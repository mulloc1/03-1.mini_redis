# Mini Redis 디버깅 입력 셋

디버깅 실행 시 기능을 빠르게 훑어보기 위한 입력 모음입니다.
각 세트는 **새 프로세스(새 REPL 세션)**에서 실행하는 것을 권장합니다.

## 0) 실행 방법

프로젝트 루트(`03-1.mini_redis`)에서:

```bash
python -m mini_redis
```

프롬프트 `mini-redis>` 에서 아래 입력 셋을 그대로 붙여 넣어 확인합니다.

---

## 1) 기본 String 명령 검증

목표: `SET/GET/DEL/EXISTS/DBSIZE/KEYS` 기본 동작 확인

입력:

```text
DBSIZE
KEYS
SET user:1 Alice
GET user:1
EXISTS user:1
DBSIZE
KEYS
DEL user:1
GET user:1
EXISTS user:1
DBSIZE
KEYS
```

기대 포인트:
- 초기 상태에서 `DBSIZE`는 `(integer) 0`, `KEYS`는 `(empty array)`
- 저장 후 `GET user:1`은 `"Alice"`
- 삭제 후 `GET user:1`은 `(nil)`

---

## 2) 따옴표/공백 값 파싱 검증

목표: 큰따옴표 값 파싱 확인

입력:

```text
SET profile:name "Alice Liddell"
GET profile:name
SET message "hello world from mini redis"
GET message
```

기대 포인트:
- 공백 포함 값이 하나의 문자열로 저장/조회됨

---

## 3) TTL 라이프사이클 검증

목표: `EXPIRE/TTL` 분기(`-2`, `-1`, 정상값, 만료 후 삭제) 확인

입력:

```text
TTL missing
SET session token
TTL session
EXPIRE session 5
TTL session
GET session
```

대기(직접 6초 정도 기다린 뒤) 추가 입력:

```text
TTL session
GET session
EXISTS session
```

기대 포인트:
- 없는 키 `TTL`은 `(integer) -2`
- TTL 미설정 키는 `(integer) -1`
- 만료 후 `GET`은 `(nil)`, `EXISTS`는 `(integer) 0`

---

## 4) TTL 즉시 만료(0 이하) 검증

목표: `EXPIRE key 0` / 음수 처리 확인

입력:

```text
SET temp v
EXPIRE temp 0
GET temp
SET temp2 v
EXPIRE temp2 -5
EXISTS temp2
```

기대 포인트:
- 키가 존재하면 `EXPIRE ... 0` 또는 음수에서 즉시 만료되어 삭제됨

---

## 5) LRU 제거 + INFO memory 검증

목표: `maxmemory` 초과 시 LRU 키 자동 제거 및 evicted 카운트 확인

입력:

```text
CONFIG SET maxmemory 16
SET a "xxxx"
SET b "yyyy"
SET c "zzzz"
GET a
SET d "wwww"
EXISTS b
INFO memory
```

기대 포인트:
- `GET a`로 a를 최근 사용으로 만든 뒤 삽입하면, 오래된 키(`b`)가 제거됨
- `EXISTS b`는 `(integer) 0`
- `INFO memory`에서 `evicted_keys`가 증가

---

## 6) 단일 엔트리 OOM 검증

목표: 단일 `key+value` 자체가 `maxmemory`를 넘는 경우 확인

입력:

```text
CONFIG SET maxmemory 4
SET hello world
```

기대 포인트:
- `(error) OOM command not allowed when used_memory > 'maxmemory'`

---

## 7) CONFIG/INFO 인자 및 파싱 에러 검증

목표: 정수 파싱 실패, 잘못된 서브커맨드, 인자 오류 확인

입력:

```text
CONFIG SET maxmemory abc
CONFIG GET maxmemory
INFO cpu
CONFIG SET maxmemory
EXPIRE key not_int
```

기대 포인트:
- 정수 파싱 실패: `(error) ERR value is not an integer or out of range`
- 잘못된 CONFIG/INFO 사용: 적절한 `(error)` 반환

---

## 8) 일반 명령 에러 매트릭스

목표: unknown command / arity / quote 에러 확인

입력:

```text
FOOBAR
SET only_one_arg
SET a "unterminated
GET
DEL
EXISTS
TTL
```

기대 포인트:
- 미지원 명령: `(error) ERR unknown command ...`
- 인자 개수 오류: `(error) ERR wrong number of arguments ...`
- 따옴표 불균형: `(error) ERR unbalanced quotes in request`

---

## 9) 종합 스모크 테스트(짧은 회귀용)

목표: 주요 기능을 짧게 한 번에 점검

입력:

```text
CONFIG SET maxmemory 64
SET user:1 Alice
SET user:2 Bob
GET user:1
EXPIRE user:1 2
TTL user:1
INFO memory
KEYS
DEL user:2
DBSIZE
```

대기(3초 뒤) 추가 입력:

```text
GET user:1
TTL user:1
DBSIZE
KEYS
quit
```

기대 포인트:
- TTL 만료, 키 개수 변화, 메모리 정보, 종료 명령까지 한 흐름에서 검증 가능
