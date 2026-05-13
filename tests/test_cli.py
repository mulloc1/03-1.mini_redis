"""Tests for mini_redis CLI parsing, dispatch, and REPL behavior."""

from __future__ import annotations

import io
import unittest

from mini_redis.cli import (
    EXIT_SIGNAL,
    PROMPT,
    _fmt_bulk,
    _fmt_error,
    _fmt_info_memory,
    _fmt_integer,
    _fmt_keys,
    _tokenize,
    dispatch,
    run_repl,
)
from mini_redis.store import StoreMetrics
from tests.helpers import FakeClock, make_store


class TestTokenizer(unittest.TestCase):
    def test_tokenize_plain_whitespace_split(self) -> None:
        # 공백으로 분리된 기본 토큰 규칙을 검증한다.
        self.assertEqual(_tokenize("SET name Alice"), ["SET", "name", "Alice"])

    def test_tokenize_supports_double_quoted_value(self) -> None:
        # 큰따옴표 값은 하나의 토큰으로 유지되는지 검증한다.
        self.assertEqual(
            _tokenize('SET name "Alice Liddell"'),
            ["SET", "name", "Alice Liddell"],
        )

    def test_tokenize_ignores_extra_spaces_and_tabs(self) -> None:
        # 다중 공백/탭이 토큰 분리에 영향 없는지 검증한다.
        self.assertEqual(_tokenize("  GET\t\tname   "), ["GET", "name"])

    def test_tokenize_blank_line_returns_empty_list(self) -> None:
        # 빈 입력과 공백 입력에서 토큰이 비어있는지 검증한다.
        self.assertEqual(_tokenize(""), [])
        self.assertEqual(_tokenize("    "), [])


class TestFormatters(unittest.TestCase):
    def test_fmt_integer_and_bulk(self) -> None:
        # 정수/문자열 포매터가 Redis 스타일 문자열을 반환하는지 검증한다.
        self.assertEqual(_fmt_integer(0), "(integer) 0")
        self.assertEqual(_fmt_integer(-2), "(integer) -2")
        self.assertEqual(_fmt_bulk(""), '""')
        self.assertEqual(_fmt_bulk("abc"), '"abc"')

    def test_fmt_keys_for_empty_and_populated(self) -> None:
        # KEYS 포맷이 비어있는 경우와 다건 경우 모두 올바른지 검증한다.
        self.assertEqual(_fmt_keys([]), "(empty array)")
        self.assertEqual(_fmt_keys(["a", "b"]), '1) "a"\n2) "b"')

    def test_fmt_info_memory(self) -> None:
        # INFO memory 포맷이 3개 필드를 고정 순서로 출력하는지 검증한다.
        metrics = StoreMetrics(used_memory=42, maxmemory=1024, evicted_keys=3)
        self.assertEqual(
            _fmt_info_memory(metrics),
            "used_memory:42\nmaxmemory:1024\nevicted_keys:3",
        )

    def test_fmt_error(self) -> None:
        # 에러 포맷이 '(error) ' 접두사를 붙이는지 검증한다.
        self.assertEqual(_fmt_error("ERR sample"), "(error) ERR sample")


class TestDispatch(unittest.TestCase):
    def test_set_get_del_exists_and_dbsize(self) -> None:
        # 기본 문자열 명령 디스패치 흐름을 검증한다.
        store = make_store()
        self.assertEqual(dispatch(store, "SET name Alice"), "OK")
        self.assertEqual(dispatch(store, "GET name"), '"Alice"')
        self.assertEqual(dispatch(store, "EXISTS name"), "(integer) 1")
        self.assertEqual(dispatch(store, "DBSIZE"), "(integer) 1")
        self.assertEqual(dispatch(store, "DEL name"), "(integer) 1")
        self.assertEqual(dispatch(store, "GET name"), "(nil)")

    def test_keys_empty_and_non_empty(self) -> None:
        # KEYS 가 비어있는 경우/값이 있는 경우를 각각 검증한다.
        store = make_store()
        self.assertEqual(dispatch(store, "KEYS"), "(empty array)")
        dispatch(store, "SET user:1 a")
        dispatch(store, "SET user:2 b")
        keys_out = dispatch(store, "KEYS")
        assert isinstance(keys_out, str)
        self.assertIn('"user:1"', keys_out)
        self.assertIn('"user:2"', keys_out)

    def test_config_set_and_info_memory(self) -> None:
        # CONFIG SET maxmemory 와 INFO memory 출력 연계를 검증한다.
        store = make_store()
        self.assertEqual(dispatch(store, "CONFIG SET maxmemory 1024"), "OK")
        self.assertEqual(
            dispatch(store, "INFO memory"),
            "used_memory:0\nmaxmemory:1024\nevicted_keys:0",
        )

    def test_lru_scenario_matches_plan_example(self) -> None:
        # maxmemory 초과 시 LRU 키 제거와 evicted_keys 증가를 검증한다.
        store = make_store()
        dispatch(store, "CONFIG SET maxmemory 16")
        dispatch(store, 'SET a "xxxx"')
        dispatch(store, 'SET b "yyyy"')
        dispatch(store, 'SET c "zzzz"')
        self.assertEqual(dispatch(store, "GET a"), '"xxxx"')
        self.assertEqual(dispatch(store, 'SET d "wwww"'), "OK")
        self.assertEqual(dispatch(store, "EXISTS b"), "(integer) 0")
        self.assertEqual(
            dispatch(store, "INFO memory"),
            "used_memory:15\nmaxmemory:16\nevicted_keys:1",
        )

    def test_single_entry_oom_output(self) -> None:
        # 단일 엔트리 OOM 시 지정된 에러 문자열이 출력되는지 검증한다.
        store = make_store()
        dispatch(store, "CONFIG SET maxmemory 4")
        self.assertEqual(
            dispatch(store, 'SET hello "world"'),
            "(error) OOM command not allowed when used_memory > 'maxmemory'",
        )

    def test_expire_and_ttl_branches(self) -> None:
        # EXPIRE/TTL 의 정상 및 -1/-2 분기를 검증한다.
        clock = FakeClock()
        store = make_store(clock=clock)
        dispatch(store, "SET session abc")
        self.assertEqual(dispatch(store, "EXPIRE session 60"), "(integer) 1")
        self.assertEqual(dispatch(store, "TTL session"), "(integer) 60")
        clock.advance(20)
        self.assertEqual(dispatch(store, "TTL session"), "(integer) 40")
        dispatch(store, "SET forever x")
        self.assertEqual(dispatch(store, "TTL forever"), "(integer) -1")
        self.assertEqual(dispatch(store, "TTL missing"), "(integer) -2")
        self.assertEqual(dispatch(store, "EXPIRE missing 10"), "(integer) 0")

    def test_errors_unknown_arity_integer_and_config(self) -> None:
        # 미지원 명령/인자 개수/정수 파싱/CONFIG 분기 에러를 검증한다.
        store = make_store()
        self.assertEqual(
            dispatch(store, "FOOBAR"),
            "(error) ERR unknown command 'FOOBAR'",
        )
        self.assertEqual(
            dispatch(store, "SET only_one_arg"),
            "(error) ERR wrong number of arguments for 'set' command",
        )
        self.assertEqual(
            dispatch(store, "EXPIRE key abc"),
            "(error) ERR value is not an integer or out of range",
        )
        self.assertEqual(
            dispatch(store, "CONFIG GET maxmemory"),
            "(error) ERR unknown subcommand or wrong number of arguments for 'set'",
        )

    def test_exit_quit_and_blank(self) -> None:
        # exit/quit 신호와 빈 줄 처리가 의도대로 동작하는지 검증한다.
        store = make_store()
        self.assertIs(dispatch(store, "exit"), EXIT_SIGNAL)
        self.assertIs(dispatch(store, "QUIT"), EXIT_SIGNAL)
        self.assertIsNone(dispatch(store, ""))
        self.assertIsNone(dispatch(store, "   "))


class TestRunRepl(unittest.TestCase):
    def test_scripted_commands_write_stdout_and_prompts_to_stderr(self) -> None:
        # REPL 실행 시 응답은 stdout, 프롬프트는 stderr 로 분리되는지 검증한다.
        store = make_store()
        stdin = io.StringIO("SET a 1\nGET a\nDEL a\nexit\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_repl(store, stdin, stderr, stdout)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), 'OK\n"1"\n(integer) 1\n')
        self.assertEqual(stderr.getvalue(), PROMPT * 4)

    def test_eof_returns_zero(self) -> None:
        # EOF 입력 시 정상 종료 코드 0을 반환하는지 검증한다.
        store = make_store()
        stdin = io.StringIO("SET a 1\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_repl(store, stdin, stderr, stdout)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "OK\n")
        self.assertEqual(stderr.getvalue(), PROMPT * 2)

    def test_blank_lines_have_no_stdout(self) -> None:
        # 빈 입력 줄은 출력 없이 다음 명령 처리로 넘어가는지 검증한다.
        store = make_store()
        stdin = io.StringIO("\n\nGET a\nexit\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run_repl(store, stdin, stderr, stdout)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "(nil)\n")
        self.assertEqual(stderr.getvalue(), PROMPT * 4)


class TestDebugScenarios(unittest.TestCase):
    def test_debug_lru_flow_with_step_snapshots(self) -> None:
        # LRU 제거 흐름을 단계별 응답/메모리 상태로 추적 가능하게 검증한다.
        store = make_store()
        steps: list[tuple[str, str]] = [
            ("CONFIG SET maxmemory 16", "OK"),
            ('SET a "xxxx"', "OK"),
            ('SET b "yyyy"', "OK"),
            ('SET c "zzzz"', "OK"),
            ("GET a", '"xxxx"'),
            ('SET d "wwww"', "OK"),
            ("EXISTS b", "(integer) 0"),
            ("INFO memory", "used_memory:15\nmaxmemory:16\nevicted_keys:1"),
        ]

        transcript: list[tuple[str, str]] = []
        for command, expected in steps:
            actual = dispatch(store, command)
            assert isinstance(actual, str)
            transcript.append((command, actual))
            self.assertEqual(actual, expected)

        self.assertEqual(transcript, steps)

    def test_debug_ttl_lifecycle_with_explicit_time_ticks(self) -> None:
        # FakeClock tick 마다 TTL 값과 만료 여부를 눈으로 따라갈 수 있게 검증한다.
        clock = FakeClock(start=10.0)
        store = make_store(clock=clock)
        dispatch(store, "SET session token")
        dispatch(store, "EXPIRE session 3")

        timeline: list[tuple[str, str]] = []
        timeline.append(("t=10 TTL", dispatch(store, "TTL session")))
        clock.advance(1.0)
        timeline.append(("t=11 TTL", dispatch(store, "TTL session")))
        clock.advance(1.1)
        timeline.append(("t=12.1 TTL", dispatch(store, "TTL session")))
        clock.advance(1.0)
        timeline.append(("t=13.1 GET", dispatch(store, "GET session")))
        timeline.append(("t=13.1 EXISTS", dispatch(store, "EXISTS session")))

        self.assertEqual(
            timeline,
            [
                ("t=10 TTL", "(integer) 3"),
                ("t=11 TTL", "(integer) 2"),
                ("t=12.1 TTL", "(integer) 1"),
                ("t=13.1 GET", "(nil)"),
                ("t=13.1 EXISTS", "(integer) 0"),
            ],
        )

    def test_debug_repl_transcript_for_breakpoint_inspection(self) -> None:
        # REPL 입력/출력 transcript를 한 번에 확인할 수 있게 검증한다.
        store = make_store()
        stdin_script = (
            "SET user:1 Alice\n"
            "GET user:1\n"
            "EXPIRE user:1 1\n"
            "TTL user:1\n"
            "FOOBAR\n"
            "exit\n"
        )
        stdin = io.StringIO(stdin_script)
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run_repl(store, stdin, stderr, stdout)
        self.assertEqual(code, 0)

        stdout_lines = stdout.getvalue().splitlines()
        stderr_prompts = stderr.getvalue()
        self.assertEqual(
            stdout_lines,
            [
                "OK",
                '"Alice"',
                "(integer) 1",
                "(integer) 1",
                "(error) ERR unknown command 'FOOBAR'",
            ],
        )
        self.assertEqual(stderr_prompts, PROMPT * 6)

    def test_debug_error_matrix_for_dispatch(self) -> None:
        # 에러 명령 매트릭스를 고정해 디버깅 시 실패 지점을 즉시 식별 가능하게 검증한다.
        store = make_store()
        cases: list[tuple[str, str]] = [
            ("SET only_one_arg", "(error) ERR wrong number of arguments for 'set' command"),
            ("EXPIRE a nope", "(error) ERR value is not an integer or out of range"),
            ("CONFIG GET maxmemory", "(error) ERR unknown subcommand or wrong number of arguments for 'set'"),
            ('SET a "unterminated', "(error) ERR unbalanced quotes in request"),
        ]

        for command, expected in cases:
            with self.subTest(command=command):
                self.assertEqual(dispatch(store, command), expected)


if __name__ == "__main__":
    unittest.main()
