# Mini Redis

Redis 스타일 출력과 REPL을 갖춘 **인메모리 키–값 저장소** 학습용 구현입니다. 해시맵(체이닝), 이중 연결 리스트(LRU), 최소 힙(TTL)을 표준 라이브러리의 dict/heapq로 대체하지 않고 직접 구성합니다.

## 요구 사항

- Python **3.14** 이상을 가정합니다.

## 실행

프로젝트 루트를 `03-1.mini_redis` 로 두고 모듈로 실행합니다.

```bash
cd 03-1.mini_redis
python -m mini_redis
```

프롬프트는 `mini-redis>` 이며, `exit` · `quit` · **EOF(Ctrl-D)** 로 종료하면 종료 코드 `0` 입니다. 명령어 이름은 **대소문자 무시**입니다(`SET` / `set` 동일). 키와 값 문자열은 **대소문자를 구분**합니다.

## 테스트

추가 패키지 없이 표준 `unittest` 로 검증합니다.

```bash
cd 03-1.mini_redis
python -m unittest discover -s tests -p 'test_*.py' -v
```

(`pytest.ini` 의 `pythonpath` 설정은 pytest 사용 시 경로 보조용입니다.)

---

## 설계 고정 결정 (Locked Decisions)

본 구현은 `docs/plan.md` §2와 동일한 전제를 둡니다.

| 항목 | 결정 |
| --- | --- |
| 명령 대소문자 | **case-insensitive** (`SET`/`set`/`Set` 동일) |
| 키/값 대소문자 | **case-sensitive** 유지 |
| 값 파싱 | **공백 없는 토큰** 또는 **큰따옴표로 감싼 값**(이스케이프 미지원) |
| 해시 함수 | **FNV-1a 32-bit** 직접 구현 |
| 해시맵 초기 버킷 크기 | **16** |
| 해시맵 로드 팩터 | **> 0.75 → 버킷 2배 확장** + 전체 rehash |
| LRU 방향 | **front = MRU, back = LRU** (`SET`/`GET` 성공 시 MRU 쪽으로 이동) |
| TTL 자료구조 | **최소 힙 + lazy deletion** |
| `used_memory` 산정 | `Σ( len(utf8(key)) + len(utf8(value)) )` 만 누적(자료구조 오버헤드 제외) |
| `maxmemory` 초기값 | **0** (무제한) |
| 메모리 단위 | **바이트 정수만** (`1k` 등 접미사 없음) |
| `KEYS` 순서 | 정렬 비요구, **삽입·해시 순회 순서** 그대로 |
| 종료 명령 | `exit` 또는 `quit`(대소문자 무시) |

---

## 지원 명령

| 입력 | 설명 |
| --- | --- |
| `SET key value` | 키에 값 저장. 성공 시 `OK`. 기존 키 덮어쓰기 시 **TTL 제거** |
| `GET key` | 값 조회. 없거나 만료면 `(nil)`, 있으면 `"값"` 형태 |
| `DEL key` | 삭제. `(integer) 1` / `(integer) 0` |
| `EXISTS key` | 존재 여부. `(integer) 1` / `(integer) 0` |
| `DBSIZE` | 키 개수. `(integer) N` |
| `KEYS` | 전체 키(패턴 없음). 없으면 `(empty array)` |
| `CONFIG SET maxmemory bytes` | 최대 메모리(바이트). `0` = 무제한 |
| `INFO memory` | `used_memory` / `maxmemory` / `evicted_keys` 세 줄 |
| `EXPIRE key seconds` | TTL 설정(초). 없는 키 `(integer) 0`, `seconds ≤ 0` 이면 즉시 삭제 후 `(integer) 1` |
| `TTL key` | 남은 초. 없음 `-2`, TTL 없음 `-1`, 그 외 `(integer) N` |

### 오류 응답 요약

| 상황 | 출력 형식 |
| --- | --- |
| 미지원 명령 | `(error) ERR unknown command '<cmd>'` |
| 인자 개수 오류 | `(error) ERR wrong number of arguments for '<cmd>' command` |
| 정수 파싱 실패 | `(error) ERR value is not an integer or out of range` |
| 단일 엔트리 OOM | `(error) OOM command not allowed when used_memory > 'maxmemory'` |
| `CONFIG`/`INFO` 하위 명령 불일치 | `(error) ERR unknown subcommand or wrong number of arguments for 'set'` |
| 닫히지 않은 `"` | `(error) ERR unbalanced quotes in request` |

---

## 출력 예시 요약

```
mini-redis> SET name "Alice"
OK
mini-redis> GET name
"Alice"
mini-redis> GET missing
(nil)
mini-redis> DBSIZE
(integer) 1
mini-redis> KEYS
1) "name"
mini-redis> CONFIG SET maxmemory 1024
OK
mini-redis> INFO memory
used_memory:9
maxmemory:1024
evicted_keys:0
mini-redis> EXPIRE name 60
(integer) 1
mini-redis> TTL name
(integer) 60
```

`INFO memory` 의 숫자는 저장된 키/값에 따라 달라집니다.

---

## 한계 및 비범위

- **디스크 영속화 없음**: 프로세스 종료 시 데이터가 사라집니다.
- **네트워크 서버 없음**: 로컬 REPL만 제공합니다.
- **`KEYS` 패턴 매칭 없음**: 전체 나열만 합니다.
- **값 파싱**: 큰따옴표 안의 `\` 이스케이프·중첩 따옴표는 지원하지 않습니다.
- **`used_memory`**: 키·값 UTF-8 바이트 합만 반영하며, 노드·버킷 등 내부 오버헤드는 포함하지 않습니다.
- **TTL 표시**: 내부 시계는 `time.monotonic` 기반이며, 남은 시간은 `math.ceil` 로 정수 초로 보고합니다.

자세한 과제 정의는 `docs/subject.md`, 구현·테스트 계획은 `docs/plan.md` 를 참고하세요.
