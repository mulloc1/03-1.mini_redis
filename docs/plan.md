# Mini Redis 구현 계획 (plan.md)

본 문서는 `docs/subject.md` 의 요구사항과 레포지토리 `.cursorrules` 의 코딩/구조 규칙을 동시에 만족하는 단계별 구현 계획이다. 「Minimal-First / YAGNI」 원칙(.cursorrules §3)에 따라 **요구사항을 만족하는 최소 구성**으로 시작하고, 보너스 과제(subject §5)는 본 과제 완료 이후 별도 단계로 분리한다.

---

## 1. 목표 요약

- Python 3.14 기준 CLI(REPL) 기반 Mini Redis 애플리케이션을 **단일 패키지**(`mini_redis`)로 구현한다.
- 실행 진입점은 `python -m mini_redis` 로 통일하고, `mini-redis>` 프롬프트의 **REPL** 환경을 제공한다(subject §4.5).
- 데이터는 **인메모리** 저장이며, 외부 직렬화/영속화는 본 과제 범위 외다.
- 핵심 자료구조(이중 연결 리스트·해시맵·최소 힙)는 **내장 컬렉션을 대체하지 않고 직접 구현**한다(subject §4.1).
- 모든 함수 시그니처에 **타입 힌트**를 적용한다(.cursorrules §4 Type Hinting).
- 출력은 Redis 스타일 문자열(`OK`, `(nil)`, `(integer) N`, `(error) ...`)로 통일한다(subject §4.2).

---

## 2. 사전 고정 결정 (Locked Decisions)

subject 가 「난이도에 따라 단순 규칙 가능」 등으로 열어둔 항목, 그리고 본 과제 범위에서 미리 굳혀둘 결정.


| 항목                              | 결정                                                                       | 근거                                             |
| ------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------- |
| 명령 대소문자 (subject §4.5)          | **case-insensitive** (`SET`/`set`/`Set` 동일)                              | 실제 Redis CLI 관례, 사용자 입력 편의                     |
| 키/값 대소문자                        | **case-sensitive** 유지                                                    | Redis 의미론 보존                                   |
| 값 파싱 (subject §4.5)             | **공백 없는 토큰 + 큰따옴표 감싼 값** 둘 다 지원(이스케이프 미지원)                               | subject §4.5 "최소" 요구 + 단일 따옴표/이스케이프 도입은 YAGNI  |
| 해시 함수 (subject §4.1)            | **FNV-1a 32-bit** 직접 구현                                                  | 구현 단순·분산도 충분, 외부 라이브러리 무의존                     |
| 해시맵 초기 버킷 크기                    | **16**                                                                   | 메모리/충돌 균형, 2배 확장과 자연스러움                        |
| 해시맵 로드 팩터 임계치 (subject §4.1)    | **> 0.75 → 버킷 2배 확장**                                                    | subject 명시                                     |
| LRU 방향 (subject §4.1)           | **front = MRU, back = LRU** (`move_to_front` 가 SET/GET 성공 시 호출)          | subject §4.1 명시 메서드와 정합                        |
| TTL 자료구조 (subject §4.4)         | **최소 힙 + lazy deletion**                                                 | 가장 빠른 만료를 O(log N) 으로 찾고, 갱신/삭제는 stale 표시로 단순화 |
| `used_memory` 산정 (subject §4.3) | `Σ( len(utf8(key)) + len(utf8(value)) )` 만 누적, 자료구조 오버헤드 제외              | subject §4.3 공식 그대로                            |
| `maxmemory` 초기값                 | **0** (무제한)                                                              | subject §4.3 "0 = 무제한"                         |
| 메모리 단위 (subject §4.3)           | **바이트 정수만** 수용 (`1k`/`1m` 등 접미사 미지원)                                     | subject 명시(바이트 단위) + YAGNI                     |
| `KEYS` 정렬 (subject §4.2)        | 정렬·순서 비요구. **삽입/해시 순회 순서 그대로** 출력                                        | subject 명시                                     |
| 종료 명령 (subject §4.5)            | `**exit` 또는 `quit`** (대소문자 무시)                                           | subject 명시                                     |
| 테스트 러너                          | 표준 `unittest` (`python -m unittest discover -s tests -p 'test_*.py' -v`) | .cursorrules §5 Stdlib Test Runner             |


---

## 3. 디렉터리 / 모듈 구성

subject §4.1 ‘자료구조 3종 분리 구현’ + §4.2~§4.4 ‘명령/메모리/TTL’ 책임을 따른다. .cursorrules §3 에 따라 **하위 디렉터리 없이 단일 패키지 안에 평탄(flat)** 하게 둔다(증거 후 분리). `tests/` 는 `mini_redis/` 모듈을 미러링한다(.cursorrules §5).

```
03-1.mini_redis/
├── README.md                 # 실행법 · 명령 표 · 출력 예시
├── docs/
│   ├── subject.md
│   └── plan.md               # (본 문서)
├── pytest.ini                # pythonpath = . tests
├── mini_redis/
│   ├── __init__.py
│   ├── __main__.py           # python -m mini_redis → main() 위임
│   ├── main.py               # 진입 조립 · REPL 루프 호출
│   ├── linked_list.py        # 이중 연결 리스트 (subject §4.1)
│   ├── hashmap.py            # 해시맵 (체이닝, 직접 해시) (subject §4.1)
│   ├── heap.py               # 최소 힙 (TTL 용) (subject §4.1)
│   ├── store.py              # 핵심 엔진: 자료구조 조합 + LRU + TTL + 메모리
│   ├── cli.py                # 입력 토크나이저 · 명령 디스패치 · Redis 스타일 출력 포매팅
│   └── errors.py             # 도메인 예외 (CommandError, OOMError 등)
└── tests/
    ├── helpers.py            # 임시 스토어 팩토리 · 고정 시계 주입 픽스처
    ├── test_linked_list.py
    ├── test_hashmap.py
    ├── test_heap.py
    ├── test_store.py
    └── test_cli.py
```

**분리 정당화** (.cursorrules §3 ‘증거 후 분리’ 관점):

- `linked_list.py` / `hashmap.py` / `heap.py` — subject §4.1 가 세 자료구조를 **명시적으로 분리 구현**하라고 요구하고, 각각 독립 테스트 대상이다.
- `store.py` ↔ `cli.py` 분리 — `store` 는 **순수 로직(Python 값 반환)**, `cli` 는 **I/O(REPL 입출력) + Redis 문자열 포매팅** 으로 .cursorrules §4 SRP("순수 로직과 I/O 를 분리")에 정합.
- 그 외 `parser`/`commands` 같은 추가 모듈은 본 단계에서는 두지 않는다(증거 부족, 단일 사용처).

---

## 4. 자료구조 설계 (subject §4.1)

### 4.1 이중 연결 리스트 (`linked_list.py`)


| 항목        | 설계                                                                                                       |
| --------- | -------------------------------------------------------------------------------------------------------- |
| `Node` 필드 | `prev: Node | None`, `next: Node | None`, `data: Any`                                                    |
| 보조 필드     | head/tail 센티넬을 두면 경계 분기 제거 가능(택1). 본 구현은 **센티넬 없이 `head`/`tail` 만 보유**                                   |
| 메서드       | `insert_front`, `insert_back`, `remove_front`, `remove_back`, `remove_node(node)`, `move_to_front(node)` |
| 복잡도       | 모든 연산 **O(1)** (subject §4.1 명시)                                                                         |
| 용도        | (a) LRU 추적용 — `data = key`. (b) 해시맵 버킷의 충돌 체이닝 재사용 가능(subject §4.1 권장)                                   |


### 4.2 해시맵 (`hashmap.py`)


| 항목      | 설계                                                                                                                                      |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| 메서드     | `put(key, value)`, `get(key) -> Any | None`, `remove(key) -> bool`, `contains(key) -> bool`, `keys() -> Iterator[str]`, `size() -> int` |
| 해시 함수   | **FNV-1a 32-bit** (`offset=2166136261`, `prime=16777619`) — `key` 의 UTF-8 바이트를 순회. 분포는 균등, 외부 의존 없음                                     |
| 버킷 자료구조 | 길이 N 의 리스트(파이썬 `list`는 보조용)에 **이중 연결 리스트(§4.1)** 인스턴스 또는 `(key, value)` 노드 체인                                                           |
| 충돌 처리   | **체이닝** (subject §4.1 명시)                                                                                                               |
| 확장 정책   | `size / buckets > 0.75` 직후 **버킷 2배 확장 + 전체 rehash**                                                                                     |
| 비공개 헬퍼  | `_index(key)`, `_resize()` (.cursorrules §4 Module Helpers)                                                                             |


> 본 과제는 **내장 dict 대체 금지**(subject §4.1). 본 모듈만 `store.py` 에서 키-값 저장에 사용한다.

### 4.3 최소 힙 (`heap.py`)


| 항목    | 설계                                                                           |
| ----- | ---------------------------------------------------------------------------- |
| 메서드   | `push(item)`, `pop() -> T`, `peek() -> T`, `size() -> int`                   |
| 내부    | `_heapify_up`, `_heapify_down` 직접 구현 (subject §4.1 명시)                       |
| 요소 형태 | `(expire_at: float, key: str)` 튜플 — `expire_at` 기준 최소힙 (subject §4.1 TTL 명시) |
| 비교    | 튜플 자연 비교(`expire_at` 우선)                                                     |
| 저장소   | 파이썬 `list` 의 인덱스 산술 (`parent=(i-1)//2`, `left=2i+1`, `right=2i+2`)           |


> 보너스(§5) 의 **동적 배열**을 채택하면 힙 저장소를 그 위로 교체하는 단일 변경점만 둔다.

---

## 5. 데이터 모델 (`store.py` 내부)


| 클래스/구조         | 필드                                                                    | 비고                                                            |
| -------------- | --------------------------------------------------------------------- | ------------------------------------------------------------- |
| `Entry`        | `key: str`, `value: str`, `expire_at: float | None`, `lru_node: Node` | `lru_node.data == key` 로 양방향 참조. `expire_at = None` 이면 TTL 없음 |
| `StoreMetrics` | `used_memory: int`, `maxmemory: int`, `evicted_keys: int`             | `INFO memory` 의 정확한 3개 항목과 1:1 대응 (subject §4.3)              |


직렬화는 본 과제 범위 외. dataclass 사용 권장(.cursorrules §4 Type Hinting).

---

## 6. 스토어 엔진 (`store.py`)

자료구조 3 종을 조합한 **순수 로직 계층**. CLI 와 무관하게 Python 값(`str`/`int`/`None`/`list[str]`)을 반환한다(.cursorrules §4 SRP). 시계는 `clock: Callable[[], float] = time.monotonic` 주입으로 테스트 결정성을 확보한다(.cursorrules §5 Testing Determinism).


| 메서드                                  | 동작                                                                                                                                                                                                    |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `set(key, value) -> None`            | (1) 만료 검사 → (2) 기존 키면 TTL 삭제·이전 값 메모리 차감 → (3) 신규 엔트리 메모리가 `maxmemory` 초과면 `OOMError` → (4) `hashmap.put` + `lru.insert_front` + `used_memory` 가산 → (5) `used_memory > maxmemory` 인 동안 **LRU 제거**(§7) |
| `get(key) -> str | None`             | 만료된 키는 **삭제 후 `None`** (LRU 갱신 없음, subject §4.2). 성공 시 `lru.move_to_front`                                                                                                                            |
| `delete(key) -> int`                 | 데이터·LRU 에서 즉시 제거, TTL 힙은 lazy 처리(§7.2). 성공 `1` / 미존재 `0`                                                                                                                                              |
| `exists(key) -> int`                 | 만료 검사 후 0/1                                                                                                                                                                                           |
| `dbsize() -> int`                    | 만료된 키는 조회 시점에 제거(주기적 lazy expire, §7.2). 반환은 `hashmap.size()`                                                                                                                                         |
| `keys() -> list[str]`                | `hashmap.keys()` 스냅샷 (만료 키 lazy 제거 후)                                                                                                                                                                 |
| `set_maxmemory(bytes_: int) -> None` | `bytes_ < 0` 이면 도메인 예외. 0 은 무제한. 설정 직후 초과면 LRU 제거 실행                                                                                                                                                  |
| `info_memory() -> StoreMetrics`      | 현재 메트릭 스냅샷                                                                                                                                                                                            |
| `expire(key, seconds: int) -> int`   | 키 없음 `0`, `seconds <= 0` 이면 즉시 삭제 후 `1`, 정상이면 `expire_at = now + seconds` 갱신·힙에 push, `1` (subject §4.4)                                                                                              |
| `ttl(key) -> int`                    | 키 없음 `-2`, TTL 없음 `-1`, 있으면 `max(0, ceil(expire_at - now))`                                                                                                                                           |


### 6.1 메모리 카운터 정합성

- 모든 추가/삭제 경로에서 **단 한 번**의 `used_memory` 갱신만 수행 → 회귀 위험 최소화.
- `len(s.encode("utf-8"))` 결과를 `Entry` 생성 시 캐싱해 SET 덮어쓰기·DEL·LRU 제거에서 동일 값을 차감.

---

## 7. LRU · TTL 정책 상세 (subject §4.3, §4.4)

### 7.1 LRU 제거 흐름

1. `SET` 으로 `used_memory > maxmemory` 가 된 직후 진입.
2. `lru.remove_back()` 으로 LRU 키를 꺼낸다 (back = LRU 끝).
3. 해시맵에서 엔트리 조회 → `used_memory` 차감 → `hashmap.remove(key)` → `evicted_keys += 1`.
4. `used_memory <= maxmemory` 가 될 때까지 반복.
5. **단일 엔트리가 `maxmemory` 초과** 시 저장 자체를 거부하고 `OOMError` 발생 → CLI 는 `(error) OOM ...` 출력 (subject §4.3, §4.5).

### 7.2 TTL 만료 처리

- **저장**: `EXPIRE` 호출 시 `(expire_at, key)` 를 힙에 push. 기존 TTL 이 있으면 **새 push** 만 하고 옛 항목은 stale 로 남긴다(증분 갱신은 안 함 → 단순화).
- **즉시 검사 (lazy on access)**: `GET`/`EXISTS`/`DBSIZE`/`KEYS` 진입 시, 대상 키의 `expire_at` 만 확인해 만료면 삭제.
- **주기적 검사 (lazy on heap)**: 매 명령 처리 후 `_expire_due()` 를 1회 호출.
  - `heap.peek()` 의 `expire_at <= now` 인 동안 `heap.pop()`.
  - 꺼낸 `(expire_at, key)` 의 `expire_at` 이 **현재 엔트리의 `expire_at` 과 다르면 stale → 폐기**.
  - 같으면 정식 만료 → 데이터·LRU 제거(`evicted_keys` 에는 합산하지 않음. evicted 는 **LRU 정책에 의한 제거**만, subject §4.3).
- **DEL**: 데이터·LRU 에서만 제거, 힙은 lazy. (stale 패턴으로 다음 pop 때 자동 폐기)

### 7.3 SET 덮어쓰기와 TTL 초기화

- subject §4.2 ‘기존 키 덮어쓰기 시 기존 TTL 초기화(삭제)’ 준수.
- 구현: SET 진입 시 기존 `Entry.expire_at = None` 으로 리셋. 힙의 잔여 엔트리는 stale 로 다음 pop 때 폐기.

---

## 8. CLI 명세 (`cli.py`, subject §4.5)

### 8.1 토크나이저

- 공백 분리 + **큰따옴표** 로 감싼 값은 단일 토큰. 이스케이프 미지원(YAGNI).
- 예: `SET name "Alice Liddell"` → `["SET", "name", "Alice Liddell"]`.

### 8.2 디스패치 표


| 입력 형식                        | 호출                    | 응답                                 |
| ---------------------------- | --------------------- | ---------------------------------- |
| `SET key value`              | `store.set`           | `OK`                               |
| `GET key`                    | `store.get`           | `"value"` 또는 `(nil)`               |
| `DEL key`                    | `store.delete`        | `(integer) 1` / `(integer) 0`      |
| `EXISTS key`                 | `store.exists`        | `(integer) 1` / `(integer) 0`      |
| `DBSIZE`                     | `store.dbsize`        | `(integer) N`                      |
| `KEYS`                       | `store.keys`          | 인덱스 라벨 목록(§9.2) 또는 `(empty array)` |
| `CONFIG SET maxmemory bytes` | `store.set_maxmemory` | `OK`                               |
| `INFO memory`                | `store.info_memory`   | 3행 출력(§9.3)                        |
| `EXPIRE key seconds`         | `store.expire`        | `(integer) 0` / `(integer) 1`      |
| `TTL key`                    | `store.ttl`           | `(integer) N` / `-1` / `-2`        |
| `exit` / `quit`              | REPL 종료               | (출력 없음) 종료 코드 `0`                  |


### 8.3 오류 출력 (subject §4.5)


| 상황                            | 출력                                                                                 |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| 잘못된 명령                        | `(error) ERR unknown command '<cmd>'`                                              |
| 인자 개수 오류                      | `(error) ERR wrong number of arguments for '<cmd>' command`                        |
| 정수 파싱 실패 (`bytes`, `seconds`) | `(error) ERR value is not an integer or out of range`                              |
| 메모리 초과 (단일 엔트리 OOM)           | `(error) OOM command not allowed when used_memory > 'maxmemory'`                   |
| `CONFIG` 미지원 서브명령             | `(error) ERR unknown subcommand or wrong number of arguments for 'set'` (Redis 관례) |


`EOF` 입력(`Ctrl-D`) 도 `exit` 와 동등 처리한다.

---

## 9. 출력 화면 양식 (Output Specification)

subject §4.2 / §4.5 의 **Redis 스타일** 을 stdout 단위까지 고정한 사양이다. 모든 응답은 **stdout** 으로만 내보내고, 오류도 `(error) ...` 접두사로 stdout 에 출력한다(`redis-cli` 의 관례와 일치). 테스트(§11)는 본 절의 문자열을 기준으로 stdout 을 캡처해 검증한다.

> 표기 규약: 정수는 `(integer) N`, 문자열은 `"..."` (큰따옴표 포함), 부재는 `(nil)`.

### 9.1 SET / GET / DEL / EXISTS

```
mini-redis> SET name "Alice"
OK
mini-redis> GET name
"Alice"
mini-redis> GET missing
(nil)
mini-redis> DEL name
(integer) 1
mini-redis> DEL name
(integer) 0
mini-redis> EXISTS name
(integer) 0
```

### 9.2 DBSIZE / KEYS

```
mini-redis> DBSIZE
(integer) 2
mini-redis> KEYS
1) "user:1"
2) "user:2"
```

키가 없을 때:

```
mini-redis> KEYS
(empty array)
```

### 9.3 CONFIG SET maxmemory / INFO memory (subject §4.3)

```
mini-redis> CONFIG SET maxmemory 1024
OK
mini-redis> INFO memory
used_memory:42
maxmemory:1024
evicted_keys:0
```

`maxmemory 0` (무제한) 상태에서도 동일한 3줄을 출력한다.

### 9.4 EXPIRE / TTL (subject §4.4)

```
mini-redis> SET session "abc"
OK
mini-redis> EXPIRE session 60
(integer) 1
mini-redis> TTL session
(integer) 60
mini-redis> TTL missing
(integer) -2
mini-redis> SET forever "x"
OK
mini-redis> TTL forever
(integer) -1
mini-redis> EXPIRE missing 10
(integer) 0
```

### 9.5 LRU 제거 흐름 예시 (subject §4.3)

```
mini-redis> CONFIG SET maxmemory 16
OK
mini-redis> SET a "xxxx"        # 5B (key 1 + value 4)
OK
mini-redis> SET b "yyyy"        # 5B (총 10B)
OK
mini-redis> SET c "zzzz"        # 5B (총 15B)
OK
mini-redis> GET a               # a 가 MRU 로 이동
"xxxx"
mini-redis> SET d "wwww"        # 5B → 20B > 16B → LRU(b) 제거
OK
mini-redis> INFO memory
used_memory:15
maxmemory:16
evicted_keys:1
mini-redis> EXISTS b
(integer) 0
```

### 9.6 단일 엔트리 OOM

```
mini-redis> CONFIG SET maxmemory 4
OK
mini-redis> SET hello "world"
(error) OOM command not allowed when used_memory > 'maxmemory'
mini-redis> DBSIZE
(integer) 0
```

### 9.7 잘못된 입력

```
mini-redis> FOOBAR
(error) ERR unknown command 'FOOBAR'
mini-redis> SET only_one_arg
(error) ERR wrong number of arguments for 'set' command
mini-redis> EXPIRE key abc
(error) ERR value is not an integer or out of range
```

### 9.8 종료

```
mini-redis> exit
```

→ 프롬프트 종료, 종료 코드 `0`. `quit` · `Ctrl-D` 동등.

---

## 10. 단계별 구현 계획 (Phases)

각 단계는 **하나의 논리적 변경 = 한 커밋**(.cursorrules §5 Logical Commit Unit) 단위로 진행하고 Conventional Commits 접두사를 사용한다.

### Phase 0 — 프로젝트 스캐폴딩

- `mini_redis/__init__.py`, `__main__.py`, `main.py` 만 둔 빈 패키지 생성.
- `pytest.ini` 에 `pythonpath = . tests` 설정(.cursorrules §5 ‘pytest 호환’).
- `tests/helpers.py` 에 임시 스토어 팩토리 + 고정 시계(`FakeClock`) 픽스처.
- 커밋: `chore: scaffold mini_redis package and test layout`

### Phase 1 — 자료구조 3종 (subject §4.1)

- `linked_list.py` + `test_linked_list.py` — 6 메서드 O(1) 검증, 빈 리스트/단일 노드 엣지.
- `hashmap.py` + `test_hashmap.py` — 충돌 시 체이닝 동작, 로드 팩터 초과 시 2배 확장 및 rehash 결과 검증.
- `heap.py` + `test_heap.py` — `(expire_at, key)` 튜플 순서, push/pop 순서, heapify_up/down 경계.
- 커밋: `feat: add core data structures (linked list, hashmap, min heap)`

### Phase 2 — 스토어 엔진 기본 명령 (subject §4.2)

- `Entry`, `StoreMetrics` 정의.
- `store.py` 의 `set`/`get`/`delete`/`exists`/`dbsize`/`keys` + `used_memory` 카운터 (단, `maxmemory`/LRU 자동 제거는 Phase 3).
- `errors.py` — `CommandError`(인자/파싱), `OOMError` 분리.
- 테스트: `test_store.py` 의 String 명령 케이스, 메모리 카운터 가산/차감, SET 덮어쓰기 시 카운터 정합.
- 커밋: `feat: add core key-value store with memory accounting`

### Phase 3 — 메모리 제한 & LRU 자동 제거 (subject §4.3)

- `set_maxmemory`, `info_memory` 추가.
- `set` 후 `used_memory > maxmemory` 시 LRU 백엔드부터 제거 루프(§7.1).
- 단일 엔트리 OOM 분기.
- 테스트: `evicted_keys` 누적, MRU/LRU 순서 검증(GET 후 다른 키가 먼저 제거되는지), maxmemory 0 무제한 동작.
- 커밋: `feat: enforce maxmemory with lru eviction`

### Phase 4 — TTL 관리 (subject §4.4)

본 단계는 §7.2/§7.3 의 lazy 만료 정책을 코드로 옮겨 `EXPIRE`/`TTL` 두 명령을 완성한다. 시계 의존 로직이 처음 도입되므로 `clock` 주입(.cursorrules §5 Testing Determinism)과 `FakeClock` 기반 결정성 확보가 합격 조건이다. `Store.__init__` 가 이미 보유한 `_ttl_heap: MinHeap` 과 `_clock` 을 비로소 사용하기 시작한다.

#### 4-A. 작업 항목

1. **`Entry` 확장** — §5 정의에 맞춰 `expire_at: float | None = None` 필드를 추가한다. `set()` 의 신규 `Entry` 생성 경로는 항상 `None` 으로 초기화 → §7.3 ‘SET 덮어쓰기 시 TTL 초기화’ 가 별도 분기 없이 충족된다(옛 `Entry` 는 폐기되고 옛 heap 엔트리는 stale 로 다음 sweep 때 제거).
2. **`_expire_due()` 도입** (§7.2 ‘주기적 검사’):
   - `_ttl_heap.peek()` 의 `expire_at <= clock()` 인 동안 `pop()`.
   - 데이터에 키가 없거나 `entry.expire_at != popped_expire_at` 이면 **stale 로 폐기**(아무 것도 하지 않음).
   - 일치하면 정식 만료 — `_data.remove(key)` + `_lru.remove_node(entry.lru_node)` + `used_memory -= entry.entry_bytes`.
   - **`evicted_keys` 는 가산하지 않는다** (subject §4.3 정의상 evicted = LRU 정책 제거만).
3. **공개 메서드 진입부 sweep 일원화** — `set`/`get`/`delete`/`exists`/`dbsize`/`keys`/`expire`/`ttl` 모두 첫 줄에서 `self._expire_due()` 를 호출. "매 명령 1회" 의미를 단일 진입점으로 보장하며, 이후 로직은 "데이터에 남아 있는 키는 만료되지 않았다" 라는 불변식을 누릴 수 있다.
4. **`expire(key, seconds: int) -> int`**:
   - `_expire_due()` 후 `_data.get(key)` 가 `Entry` 가 아니면 `0`.
   - `seconds <= 0` 이면 즉시 삭제(데이터·LRU·`used_memory` 반영, `evicted_keys` 무변동) 후 `1`.
   - 정상 케이스: `expire_at = self._clock() + seconds` 계산 → `entry.expire_at` 갱신 → `_ttl_heap.push((expire_at, key))` → `1`.
   - 기존 TTL 이 있어도 별도 정리 없이 **덮어쓰기만** 한다. 옛 heap 엔트리는 stale 로 자연 폐기.
5. **`ttl(key) -> int`**:
   - `_expire_due()` 후 `Entry` 가 아니면 `-2`.
   - `entry.expire_at is None` 이면 `-1`.
   - 그 외 `max(0, math.ceil(entry.expire_at - self._clock()))` (소수 진행 시간에서도 정수 응답 보존).

#### 4-B. 회귀 방지 (이전 단계 보존)

- `_enforce_maxmemory()` 와 `evicted_keys` 카운터(Phase 3)는 **변경 없음**. TTL 만료 경로는 별도 통로로 분리되어 LRU 제거 카운터를 오염시키지 않는다.
- `GET` 의 만료 키 분기는 별도 코드를 두지 않는다: `_expire_due()` 가 먼저 키를 지웠으므로 `get()` 는 그저 `None` 을 반환하면 끝 — 결과적으로 **LRU 갱신이 일어나지 않는다** (subject §4.2).
- `DEL` 은 `_ttl_heap` 을 건드리지 않는다 (subject §4.4 의 "DEL 은 모든 구조에서 제거" 는 데이터·LRU 의미이며, heap 잔재는 §7.2 의 stale 규칙으로 다음 sweep 때 폐기).
- TTL 만료로 인한 메모리 해소가 같은 명령 안에서 LRU 제거를 면제시키는 효과는 자연스럽게 발생한다(set 진입부 sweep 덕분).

#### 4-C. 테스트 (`tests/test_store.py` 확장)

전 케이스 `make_store(clock=FakeClock())` 로 결정성 확보. 각 테스트 첫 줄에 검증 목적 한 줄 주석(.cursorrules §5 Test Purpose Comments).

- `EXPIRE` 미존재 키 → `0`, 데이터·메트릭 변화 없음.
- `EXPIRE key 0`, `EXPIRE key -3` (존재 키) → `1` + 즉시 삭제, `used_memory` 감소, `evicted_keys` 무변동.
- `EXPIRE` 정상 직후 `TTL` 일치 → `FakeClock.advance(20)` 후 `TTL` 감소 → ceil 동작 (`advance(0.5)` 후 정수값 변화 없음).
- `TTL` 3 종 반환값(`-2`/`-1`/`N`) 분기 각각.
- 시계 만료 시점 통과 후 임의 명령(`EXISTS`/`DBSIZE`/`KEYS`/`GET`) 호출 시 해당 키 자동 사라짐, `evicted_keys` 무변동.
- `GET` 으로 만료 키 접근 → `None` 반환 + **LRU 순서 비변경** (만료 키 외 다른 키의 LRU 위치가 동일함을 직접 단언; 예: 만료 전 back 이던 키가 만료 후에도 back 에 그대로).
- `EXPIRE` 재호출 (TTL 갱신): 옛 만료 시각 통과 시점에 키는 살아 있음(옛 heap 엔트리는 stale 로 폐기), 새 만료 시각 통과 시 비로소 삭제.
- SET 덮어쓰기 TTL 초기화: `EXPIRE k 60` → `SET k v2` → `TTL k == -1`, `advance(120)` 후에도 `EXISTS k == 1`.
- `DEL` 직후 stale heap 엔트리가 다음 `_expire_due()` 에서 자연 폐기 — 화이트박스 보조 단언으로 `store._ttl_heap.size()` 가 0 으로 수렴하는지 확인(테스트 내에서만 접근).
- TTL 만료가 `maxmemory` 초과를 해소하는 시나리오: `maxmemory` 를 빠듯하게 잡고 키 2개 채운 뒤 한 키의 TTL 만료 → 이후 `SET` 가 **LRU 제거 없이** 성공해야 한다(`evicted_keys` 변화 없음).

#### 4-D. 커밋

- `feat: add ttl management with min-heap lazy expiration`

### Phase 5 — CLI / REPL 통합 (subject §4.5)

- `cli.py` 의 토크나이저(공백 + 큰따옴표) + 명령 디스패치 + Redis 스타일 출력 포매팅.
- `__main__.py` ↔ `main.py` ↔ `cli.run_repl()` 연결.
- `exit`/`quit`/EOF 종료, 종료 코드 `0`.
- 테스트: `test_cli.py` — stdin 스크립트 주입, stdout 캡처로 §9 예시 문자열 대조. `(error)` 케이스 4 종(미지원 명령/인자 수/정수 파싱/OOM) 검증.

### Phase 6 — README / 문서 정리

- `README.md`: 실행법(`python -m mini_redis`), 지원 명령 표, 출력 예시 요약, 한계(영속화 없음 등).
- 본 plan 의 §2 ‘고정 결정’ 표를 README 에도 동기화한다.
- 커밋: `docs: add README with usage and command reference`

### Phase 7 (선택) — 보너스 과제 (subject §5)

- 본 과제 통과 후에만 별도 브랜치/커밋으로 진행한다(.cursorrules §3 YAGNI).
- 후보 우선순위:
  1. **동적 배열** — `heap.py` 내부 저장소를 직접 구현 배열로 치환(단일 변경점).
  2. **스택/큐/덱 문서화** — `docs/STACK_QUEUE_DEQUE.md` (구현은 필요 시).
  3. **이진 트리·순회** — 별도 모듈로 추가.
  4. **BST** — 범위 조회·정렬 확장의 기반.
  5. **Pub/Sub** — `PUBLISH`/`SUBSCRIBE` 도입. REPL 의 동시성 모델 결정이 필요해 도입 전 plan 갱신 필수.
- 도입 시 본 plan 에 후속 결정 표를 추가한다.

---

## 11. 테스트 전략

- 러너: `python -m unittest discover -s tests -p 'test_*.py' -v` (.cursorrules §5).
- 결정성: 시간 의존 코드는 `clock: Callable[[], float]` 주입, 테스트는 `FakeClock`(.cursorrules §5 Testing Determinism). 외부 파일·네트워크 의존 없음(인메모리).
- 단언: `self.assertEqual` 등 `assert*` 메서드만 합격 판정에 사용(.cursorrules §5 Assert First).
- 각 테스트 함수 첫 줄에 **검증 목적 한 줄 주석**(.cursorrules §5 Test Purpose Comments).
- 공통 픽스처(스토어 팩토리·`FakeClock`)는 `tests/helpers.py` 한 곳에 모은다.

핵심 케이스 체크리스트:

- 이중 연결 리스트 6 메서드 + `move_to_front` 의 head/tail 경계.
- 해시맵 충돌 다발 입력(같은 버킷에 N 개) 후 `get`/`remove` 정확성.
- 해시맵 0.75 초과 → 버킷 2배 확장 후에도 키 보존(rehash 검증).
- 최소 힙: 무작위 N 개 push 후 pop 순서 단조 증가.
- `SET` 신규/덮어쓰기 시 `used_memory` 정확값.
- `GET` 만료 키 → 삭제 + `(nil)` + **LRU 갱신 없음**(LRU 순서 비변경 단언).
- `maxmemory` 초과 시 LRU 끝부터 제거, `evicted_keys` 누적.
- 단일 엔트리 OOM 시 데이터·메모리 모두 변경 없음.
- `EXPIRE 0` 즉시 만료, `EXPIRE` 없는 키 `0`.
- `TTL` 3 가지 반환값.
- `DEL` 후 힙의 stale 엔트리가 다음 `_expire_due` 에서 자연 폐기.
- **CLI 출력 양식 일치**: §9 의 각 명령 예시 문자열을 stdout 캡처 결과와 비교(접두사·괄호·따옴표 포함).

---

## 12. 위험 요소 / 결정 보류 항목


| 항목                         | 위험                                            | 완화책                                                                         |
| -------------------------- | --------------------------------------------- | --------------------------------------------------------------------------- |
| 직접 구현 자료구조 정합성             | LRU↔해시맵 양방향 참조 누락 시 메모리 누수·incorrect eviction | `Entry.lru_node` 한 곳에서만 참조 보유, 모든 삭제 경로에서 양쪽 함께 호출(테스트로 단언)                 |
| 해시 함수 분포                   | 의도치 않게 동일 버킷 집중 → 체이닝 성능 저하                   | FNV-1a 채택 + 버킷 확장 정책으로 평균 O(1) 보장, 충돌 다발 테스트로 회귀 방지                         |
| TTL stale heap 누적          | `EXPIRE` 반복 갱신 시 힙 크기 증가                      | lazy 폐기로 정확성은 보장. 성능 임계는 본 과제 범위 외(보너스 시 재검토)                               |
| `used_memory` 누락/이중 차감     | 카운터 회귀 시 LRU 동작 자체가 깨짐                        | `Entry` 에 캐싱된 바이트 길이만 사용, 모든 변경 경로에 단위 테스트                                  |
| 큰따옴표 입력 파싱                 | 이스케이프·중첩 누락 시 사용자 혼란                          | YAGNI: 이스케이프 미지원을 README 에 명시. 필요해지면 plan 갱신 후 도입                           |
| `monotonic` vs `time()` 선택 | 시계 점프 시 TTL 부정확                               | 본 과제는 단일 프로세스 짧은 수명 → `time.monotonic` 충분. 단, **표시되는 남은 초** 의미를 README 에 명시 |
| `INFO memory` 출력 포맷 변형     | subject §4.3 "표현 형태는 동일하면 됨" 의 모호성            | 본 plan §9.3 의 줄바꿈 포맷으로 **고정**, 테스트는 이 포맷을 단언                                |


---

## 13. 완료 정의 (Definition of Done)

- subject §2.1~§2.3 의 **10 개 명령**(SET/GET/DEL/EXISTS/DBSIZE/KEYS/CONFIG SET maxmemory/INFO memory/EXPIRE/TTL)이 §9 출력 양식 그대로 동작한다.
- 이중 연결 리스트·해시맵·최소 힙이 **내장 dict/heapq 등 대체 없이** 직접 구현되어 있고 각각 독립 테스트로 검증된다(subject §4.1).
- 해시맵 로드 팩터 > 0.75 에서 **버킷 2 배 확장**이 동작한다(subject §4.1).
- `maxmemory > 0` 에서 **LRU 자동 제거**가 동작하고 `evicted_keys` 가 누적된다(subject §4.3).
- 단일 엔트리 OOM 은 **저장 거부 + `(error) OOM ...`** 로 응답한다(subject §4.3).
- TTL 은 **최소 힙 + lazy deletion**으로 동작하며 `GET` 시 만료된 키는 **LRU 갱신 없이** 삭제·`(nil)` 응답한다(subject §4.4).
- `SET` 으로 기존 키 덮어쓰기 시 **TTL 이 초기화**된다(subject §4.2).
- REPL 이 `mini-redis>` 프롬프트로 동작하고 `exit`/`quit`/`EOF` 로 정상 종료(`0`) 한다(subject §4.5).
- 모든 공개 함수에 타입 힌트가 있고, 공개 함수에는 짧은 docstring 이 있다(.cursorrules §4).
- `python -m unittest discover -s tests -p 'test_*.py' -v` 가 추가 패키지 없이 통과한다(.cursorrules §5).
- `README.md` 가 실행법·지원 명령·출력 예시·한계(영속화 없음)를 포함한다.

