# HERMOD — Independent Browser Controller

> **Codex implementation specification · v1.0 · 2026-10-17 (Asia/Seoul)**  
> Owner: single-user Raspberry Pi environment  
> Parent system: **Heimdall** (`https://github.com/exwaiz/heimdall`, default branch `main`)  
> Proposed independent repository: **`exwaiz/hermod`** (creation is part of implementation, not yet performed)  
> Python package: `hermod` · systemd: `hermod.service` · product name: **Hermod**  
> Status: **DESIGN ONLY**. This document does **not** assert that code, service, repository, or ChatGPT browser session has already been created.

---

## 0. 핵심 요약 / 개발자에게 먼저 읽힐 내용

**Hermod는 Heimdall에서 호출하는 독립 Browser Controller다.** 사용자의 Telegram 자연어 메시지를 직접 해석하거나 AI 답변을 만들지 않는다. Hermod는 구조화된 작업 요청을 받아 Chromium/Playwright 브라우저 세션을 제어하고 **검증 가능한 작업 상태와 결과**를 Heimdall에 돌려준다.

사용자의 최종 비전은 다음과 같다.

1. 사용자가 이동 중 Telegram에 갑자기 떠오른 질문을 전송한다.
2. Heimdall이 기존 주제/Knowledge/대화방 카탈로그에서 가장 관련성 높은 대화방을 찾는다.
3. 적절한 백엔드가 Codex면 기존 Codex 스레드로, ChatGPT 웹이면 Hermod에 해당 웹 대화방을 열도록 요청한다.
4. *허용되는 인터페이스에서* 사용자 질문을 전송하고 응답을 확인하여 Telegram으로 회신한다.
5. 다음 질문에서도 같은 주제와 대화방을 재사용한다.

**실현 가능성과 서비스 이용 허용은 서로 다른 문제다.** 브라우저 제어 자체는 기술적으로 구현 가능하지만, 현재 OpenAI 소비자용 이용약관은 ChatGPT 서비스에서 데이터나 Output을 자동·프로그래밍 방식으로 추출하는 행위를 금지한다(2026-10-17 기준). 따라서 **ChatGPT 웹에 대한 무인 응답 수집/회수는 기본 구현 범위에서 비활성화한다.** 공식 데이터 내보내기 기반 로컬 인덱스와 사용자 직접 이어가기(handoff)를 먼저 구현한다. 동일한 브라우저 엔진의 자동 송수신 기능은 **그 기능이 허용된 테스트 사이트 또는 명시적으로 허가된 서비스**에서 완성·검증한다. ChatGPT 관련 기능은 사용 조건 검토 후 별도 승인/결정으로 확장할 수 있도록 인터페이스만 분리한다. CAPTCHA·보안 확인·속도 제한 우회, 숨겨진 ChatGPT API 호출, 인증 토큰 추출은 범위 밖이다.

**중요: Codex 사용량 보호.** Hermod의 일상 작업에 Codex 모델 호출을 사용하지 않는다. Python의 결정적 코드와 로컬 DB로 브라우저 작업을 수행한다. Codex는 주로 이 프로젝트를 **개발**할 때 이용한다. 선택적 AI 라우터는 Heimdall의 별도 기능이며 Hermod 내부에 두지 않는다.

---

## 1. 기존 Heimdall 현황 및 불변조건

2026-10-17 기준 공개 `main`의 코드/문서 확인 사항:

- Raspberry Pi 4 Model B 4GB, Debian 13 trixie, ARM64, Python 3.13 계열, 계정 `haaland` 환경으로 운영·테스트된 프로젝트.
- `heimdall-bridge.service`와 `heimdall-backup.timer`를 사용하며 Kakao-Radar와는 완전히 별도로 운영한다.
- Codex App Server 고정 버전 및 기존 `.codex` 스레드 handoff/lock 정책을 유지한다.
- Telegram 개인 채팅 owner `user_id`/`chat_id` 검증, 업데이트 중복방지, SQLite WAL, durable job/outbox, unknown/uncertain 시 자동 재실행 방지가 있다.
- `/knowledge auto on|off`, `/knowledge test`, `/knowledge status`에 대응하는 **Auto-Memory 검색·주입 기능은 이미 코드와 배포 문서에 존재**한다. 저장은 별개이고 자동 캡처는 아직 미구현이다. Hermod가 이 기능을 중복 구현하지 않는다.
- `scripts.smoke_temporary`에서 Playwright/Chromium을 이용한 **로컬 테스트 페이지 클릭과 PNG 저장이 성공했다고 기록**되어 있다. **ChatGPT 실제 로그인/자동 송수신 성공을 뜻하지 않는다.**
- 기존 `/mode network`는 Codex 작업에 부여되는 30분짜리 강한 권한이다. **Hermod를 작동시키기 위해 이 모드를 자동으로 켜면 안 된다.** Hermod는 독립 OS 프로세스/정책으로만 접근한다.

**반드시 보존할 것:**

1. `heimdall-bridge.service`, 카카오 레이더의 모든 서비스/상태/파일.
2. `/home/haaland/.codex`, 기존 `personal-agent` 스레드와 인증 정보.
3. 기존 Heimdall 데이터베이스의 세션, Knowledge, 작업, outbox 및 백업 정책.
4. `/database`, `/select`, `/new`, `/ask`, `/knowledge`, `/memory`, `/mode` 등 명령 의미와 레거시 동작.
5. 원래 Telegram 소유자 인증 및 단일 실행/재전송 방지 원칙.

### 1.1 설계상의 주요 차이

| 컴포넌트 | 책임 | 명시적 비책임 |
|---|---|---|
| Heimdall | Telegram gateway, 사용자 인증, 의도/대화방 라우팅, Auto-Memory, 작업·전송 관리 | 브라우저 쿠키 읽기, Playwright 실행 상세 구현 |
| Hermod | 웹 브라우저 lifecycle, 인증 상태 점검, URL 탐색, 허가된 브라우저 동작, 결과 검증 | Telegram 직접 송신, LLM 라우팅 판단, Knowledge 저장 |
| Codex | 코드를 개발·테스트; 별도의 기존 Codex 세션에서 개발/추론 | 매 일반 질문마다 브라우저를 조작하거나 별도 보안권한 획득 |
| ChatGPT 웹 | 사용자 소유 웹 서비스 및 대화 화면 | 공식 API와 동일한 연결이 보장된 것으로 가정하지 않음 |

---

## 2. 범위 정의

### 2.1 Must-have (v1)

- Hermod를 **별도 Git 저장소, Python 패키지, systemd 서비스**로 구축.
- Chromium/Playwright 실행 환경을 **현재 Pi에서 먼저 탐지**. 설치 기록을 추측하지 않고 실제 binary/architecture/version 실행 확인.
- **독립 인증 프로필** 및 격리된 OS 계정으로 로그인 세션을 보호. 필요 시 사용자가 직접 로그인할 수 있도록 안전한 수동 절차 제공.
- **Unix Domain Socket(UDS)** 기반 버전 고정 로컬 RPC. 공용 HTTP 포트는 개설하지 않음.
- 상태조회, 웹 열기, URL/출처 검증, 대화방 열기, 인증 세션 상태조회, 스크린샷의 안전한 **진단용 메타데이터**.
- 작업 큐, 명시적 타임아웃, 취소, crash recovery, 영속 idempotency, `uncertain` 관리.
- 로컬 가짜 웹 대화 서비스에서 검색·방 이동·사용자 메시지 전송·모델 응답 스트리밍·완료 감지·결과 회수까지 **실제 Playwright**로 검증.
- Heimdall에서 Hermod의 상태/작업 결과를 조회하는 얇은 어댑터와 owner-only Telegram 제어 기능.
- ChatGPT 기록은 공식 내보내기 데이터 기반으로 **Heimdall 대화 카탈로그에서 검색**하고, 식별된 기존 웹 대화방으로 수동 handoff 제공.
- 리소스 상한, 보안, 테스트, 배포/롤백, 관측성 문서화.

### 2.2 Target vision / gated capability

- `navigate → locate → compose → submit → wait → retrieve`라는 일반화된 web-conversation driver.
- Provider별 feature capability: `OPEN`, `SEARCH`, `COMPOSE`, `SUBMIT`, `COLLECT`, `ATTACH`, `READ_HISTORY`.
- **ChatGPT provider의 `SUBMIT`/`COLLECT`는 v1에서 `disabled / policy_review_required`**. 이를 숨겨서 구현하거나 활성화하지 않는다. 제공 가능성과 정책 확인을 분리해 기록한다.
- 허용된 서비스에서 `SUBMIT`/`COLLECT` 자동화가 승인되면 인터페이스는 변경 없이 Provider policy만 확장할 수 있도록 한다.

### 2.3 Out of scope (v1)

- Browser 로그인 정보·쿠키·ChatGPT 응답을 GitHub로 백업/커밋.
- 매 요청마다 Codex 호출, 별도 OpenAI API 키 도입, 기존 Codex 인가/로그인 세션 탈취.
- ChatGPT 내부 미공개 API를 직접 호출하거나 reverse-engineer하기.
- CAPTCHA·보안 경고·MFA·rate-limit 우회, stealth fingerprint/undetected-chromedriver 우회.
- 임의 도메인 탐색, 네트워크 프록시나 공개 디버깅 포트 개방.
- 페이지 콘텐츠를 쉘 명령, 권한 변경, 비밀정보 읽기 지시로 해석.
- 백그라운드 무제한 크롤링, 전체 대화방 스크래핑, 대량 메시지 자동 전송.
- 웹 계정·대화 삭제, 공유, 구매, 결제, 외부 전송 등 고영향 작업.
- Telegram 파일·음성·이미지 자동 입력. 기존 Heimdall asset 기능과 혼동 금지.

---

## 3. 아키텍처

```text
┌─────────────────────────────────────────────────┐
│ User / Telegram                                  │
│ "그때 연금 포트폴리오 이야기 계속하자"            │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│ Heimdall (existing service)                      │
│ - Telegram owner auth / durable inbox-outbox     │
│ - Topic + Conversation Router                    │
│ - SQLite thread catalogue / Auto-Memory          │
│ - Backend selection / confirmation gate          │
│ - HermodClient (UDS; restricted commands)        │
└──────────┬────────────────────────┬──────────────┘
           │                        │
           ▼                        ▼
     Codex App Server        /run/hermod/hermod.sock
     (existing threads)               │
                                      ▼
┌─────────────────────────────────────────────────┐
│ Hermod (separate service and OS identity)       │
│                                                 │
│ RPC API → Job Manager → Policy Broker           │
│                         ↓                       │
│                 Browser Manager                 │
│                         ↓                       │
│          Provider Adapter Interface             │
│           ├─ ChatGPT (open/handoff only)        │
│           ├─ Local Fixture (full read/write)    │
│           └─ future permitted provider          │
│                         ↓                       │
│           Playwright → Chromium                 │
│                  (private profile)              │
└─────────────────────────────────────────────────┘
```

### 3.1 Process / privilege boundaries

- **추천 운영 보안모델:** 서비스 전용 Linux 계정 `hermod`, 브리지 접근용 그룹 `hermod-clients`, 기존 Heimdall 서비스 사용자 `haaland`에게 그룹 membership만 명시적 승인으로 부여.
- Hermod의 프로필 `/var/lib/hermod/browser-profile`은 `hermod:hermod`와 `0700`; Hermod DB/diagnostics 디렉터리도 접근 제한.
- UDS path `/run/hermod/hermod.sock`의 디렉터리 및 파일 모드는 접근 가능한 그룹만 `0770/0660`을 목표로 설정. 서비스 시작 시 owner/group/umask와 실제 접근 제어를 검사한다.
- Heimdall에 브라우저 쿠키/로컬스토리지/세션 토큰을 보내지 않는다.
- Codex가 실행하는 일반 툴/명령이 Hermod 전용 프로필이나 소켓에 접근할 수 없도록 권한/샌드박스의 실제 효과를 검증한다. **동일 사용자인 `haaland`만으로 실행하면 이 격리를 보장할 수 없다.**
- `systemd` 방어 설정(`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`, `RestrictAddressFamilies`, `DevicePolicy` 등)은 Chromium 프로세스 생성·sandbox와 충돌할 수 있으므로 안전한 범위에서 하나씩 검증. 실패했다고 임의의 `--no-sandbox`나 root 운용을 기본값으로 채택하지 않는다.
- 한 Pi에서 동일 Chromium `user_data_dir`을 사용하는 프로세스는 **하나뿐**. 별도 일반 브라우저 프로필 재사용 금지.

### 3.2 Repository layout

```text
hermod/
├── README.md
├── SPEC.md                       # 이 문서의 추후 확정본
├── SECURITY.md
├── pyproject.toml
├── .env.example                  # 절대 실제 비밀정보를 담지 않음
├── .gitignore
├── config.example.toml
├── src/hermod/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── rpc.py                    # versioned UDS protocol
│   ├── authz.py                  # local caller + capability policy
│   ├── db.py                     # durable job ledger
│   ├── jobs.py                   # state machine / reconciliation
│   ├── browser.py                # Playwright / profile lifecycle
│   ├── locator.py                # semantic UI locators
│   ├── errors.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── fixture.py
│   │   └── chatgpt.py
│   └── diagnostics.py
├── deploy/
│   ├── hermod.service
│   └── setup-permissions.sh      # privileged action documented, not silent
├── scripts/
│   ├── doctor.py
│   ├── smoke_fixture.py
│   ├── smoke_uds.py
│   └── browser_login.py          # supervised manual login tool
├── tests/
│   ├── fixtures/site/           # offline local HTML chat simulation
│   ├── test_policy.py
│   ├── test_rpc.py
│   ├── test_jobs.py
│   ├── test_browser.py
│   ├── test_adapters.py
│   └── test_heimdall_contract.py
└── docs/
    ├── OPERATIONS.md
    ├── THREAT_MODEL.md
    ├── DEPLOYMENT.md
    ├── INTEGRATION.md
    └── RUNBOOK.md
```

**선택 이유:** Hermod는 별도 `exwaiz/hermod` 저장소가 적합하다. Heimdall 소스는 Hermod 구현 상세 대신 **UDS 계약과 Client Adapter**만 갖는다. 단, Codex는 repo 생성/권한 작업을 하기 전에 사용자 계정 접근을 확인하고, 실패하면 로컬 코드 작업만 완료하여 명확히 보고한다.

---

## 4. Browser lifecycle / 로그인

### 4.1 실행 탐지

`doctor`는 다음을 보고한다. 진단 결과를 추측하거나 설치를 자동 진행하지 않는다.

- OS/architecture/available memory/free disk.
- `python`, `playwright` 패키지, Chromium/Chrome 실행파일의 실제 경로/버전.
- 테스트 전용 프로필에서 브라우저 launch, localhost 이동, 버튼 클릭, 정상 종료가 가능한지.
- 기존 네트워크, DNS, 배포 계정, UDS 경로 권한.
- 실제 browser profile을 이용한 ChatGPT 화면 접근은 **개인 계정 로그인 승인 후 선택적 확인**.
- 각 진단의 `checked`, `not_checked`, `failed`, `blocked`를 구분.

### 4.2 독립 프로필과 사용자 로그인

- `browser_type.launch_persistent_context(user_data_dir=<private dir>, ...)`를 사용하되 **정규 Chromium 개인 기본 프로필을 재사용하지 않는다**.
- 처음에는 `AUTH_REQUIRED` 상태. **소유자가 직접** 브라우저에서 로그인/MFA/보안 확인을 완료한다.
- Pi에 GUI가 없으면 소유자가 승인한 일시적인 로컬 원격 데스크톱 방식 또는 보안 SSH 터널 하에서만 수동 로그인한다. 공개 VNC/CDP 포트, 웹 공개 로그인 링크, 봇 대화창에 암호 전달 금지.
- **Codex CLI의 ChatGPT 로그인과 Hermod Chromium의 ChatGPT 웹 로그인은 서로 공유되지 않는다.** 브라우저에서 별도 로그인 확인 필요.
- 쿠키 파일, storage state, 프로필 디렉터리, debug trace에는 개인 식별/인증정보가 존재할 수 있음. 기본적으로 전체 프로필 백업/로그 저장 금지.
- 세션 만료, CAPTCHA, MFA 화면 관찰 시 `AUTH_REQUIRED` 또는 `HUMAN_ACTION_REQUIRED` 반환; 무리하게 재로그인하거나 우회 금지.
- 로그인 성공 표시만으로 ChatGPT 메시지 송수신 권한/한도/정책 적합성을 추정하지 않는다.

### 4.3 브라우저 매니저

- 최초 v1은 **단일 Chromium persistent context + 동시 foreground 작업 1개**.
- IDLE일 때 브라우저 종료 및 차후 프로필 재시작 허용. 재시작이 세션 유지를 보장하지 않으므로 `AUTH_REQUIRED` 재판정 가능.
- 사용자 세션에서 열린 URL이 allowlist를 벗어나거나 팝업·다운로드 발생 시 기본 block/close, 상태 기록.
- 허용 도메인 `chatgpt.com` 등은 strict exact host + HTTPS 기준; `*.example.com` 같은 와일드카드는 명시적 허가 없이는 금지. 로컬 fixture는 `127.0.0.1` 특정 포트만 테스트 모드에서 허용.
- **arbitrary URL / arbitrary JS / arbitrary selector / shell command**를 RPC의 외부 입력으로 받지 않는다.
- 모든 브라우저 상태는 timeout/cancel/restart 이후에도 `get_status`와 맞아야 한다.

---

## 5. Heimdall ↔ Hermod RPC 계약

### 5.1 Transport

- Unix Domain Socket **JSON Lines request-response**, 1 연결당 1 요청, UTF-8, `\n` terminated.
- Protocol `version=1`. 양쪽 버전 불일치면 `UNSUPPORTED_VERSION`, 절대 조용히 fallback하지 않음.
- 최대 요청 길이 64 KiB, 최대 응답 길이 256 KiB; 실제 장문 결과는 개인정보 노출/메시지 길이 제한을 고려해 별도 제한 및 합의된 청크 전략 적용.
- Hermod는 소켓 파일 접근 권한 및 Linux `SO_PEERCRED`가 가능한 경우 UID를 확인한다. 허용 UID는 구성에서 명시. 원격 TCP/공개 리스너 금지.
- 모든 사용자 액션은 **Heimdall에서 검증된 Telegram owner로부터 도착**해야 한다. Hermod는 Heimdall의 사용자 판단을 무작정 신뢰하는 대신 허용된 호출 프로세스를 검증한다.
- Job 요청에는 `request_id`, `idempotency_key`, `requested_by`(owner id 식별자 또는 비식별 token), `purpose`, `policy_version`을 담되 **Telegram 봇 토큰 원문은 금지**.

### 5.2 Protocol example

```json
{"version":1,"request_id":"aee8f147-4f13-4636-af0a-d7a0a5c0f456","method":"browser.status","params":{}}
```

```json
{"version":1,"request_id":"aee8f147-4f13-4636-af0a-d7a0a5c0f456","ok":true,"result":{"browser":"ready","auth":"auth_required","active_job":null,"protocol_version":1}}
```

```json
{"version":1,"request_id":"b55fcb65-4ea5-4611-933c-0ed70cd7a655","method":"jobs.create","params":{"idempotency_key":"telegram:1234567:891","provider":"chatgpt","action":"conversation.open","conversation_ref":"cgpt:abc123","mode":"manual_handoff"}}
```

```json
{"version":1,"request_id":"b55fcb65-4ea5-4611-933c-0ed70cd7a655","ok":true,"result":{"job_id":"HB-000001","state":"queued","duplicate":false}}
```

**위 `conversation_ref`는 로컬에서 등록된 내부 식별자 예시다. ChatGPT 대화 ID나 URL을 추정한 값이 아니다.**

### 5.3 v1 Methods

| Method | 동작 | Side effect | v1 허용 |
|---|---|---|---|
| `system.health` | 프로세스/DB/브라우저 상태와 버전 | 없음 | YES |
| `browser.status` | 브라우저 상태 및 로그인 확인 결과 | 없음 | YES |
| `browser.ensure` | 필요 시 브라우저 구동, 미로그인은 수동 안내 | 브라우저 구동 | YES |
| `conversation.open` via `jobs.create` | 검증된 참조의 웹 대화 열기 | navigation | YES |
| `conversation.inspect` | 대화방 식별/URL/현재 화면 상태 등 **최소 메타데이터** | 없음 | 제한 |
| `conversation.search` | 서비스가 허용한 범위의 검색, 정책별 | navigation/read | v1 ChatGPT 비활성 |
| `conversation.send` | 허용된 Provider에만 메시지 전송 | **high side effect** | local fixture YES, ChatGPT NO |
| `conversation.collect` | 허용된 Provider의 완료 답변 확인 | Output extraction | local fixture YES, ChatGPT NO |
| `jobs.get` | 영속 작업 상태 조회 | 없음 | YES |
| `jobs.cancel` | 작업 중단 요청 | 작업 중단 | YES |
| `jobs.resolve` | `uncertain` 사용자 확인 후 상태 전환 | 영속 기록 | YES, owner confirmed |
| `session.login_required` | 사용자 수동 로그인 필요 여부 | 없음 | YES |

**설계 원칙:** Router가 임의 ChatGPT URL/DOM selector를 Hermod에 전달하지 않는다. 대화방 정보는 Heimdall의 검증된 카탈로그 ID → Hermod의 Provider Adapter가 검증한 URI로만 이동한다.

### 5.4 응답/오류 규약

```json
{"version":1,"request_id":"...","ok":false,"error":{"code":"AUTH_REQUIRED","message":"manual sign-in required","retryable":false}}
```

상태 코드 표준화:

- `INVALID_ARGUMENT`, `FORBIDDEN`, `UNSUPPORTED_VERSION`, `PROVIDER_DISABLED`, `POLICY_REVIEW_REQUIRED`
- `AUTH_REQUIRED`, `HUMAN_ACTION_REQUIRED`, `NAVIGATION_FAILED`, `PAGE_MISMATCH`, `UI_CHANGED`
- `SESSION_BUSY`, `RESOURCE_EXHAUSTED`, `TIMEOUT`, `JOB_NOT_FOUND`, `DUPLICATE_REQUEST`
- `ACTION_UNCERTAIN`, `RESULT_UNCERTAIN`, `CANCELLED`, `INTERNAL_ERROR`

메시지에는 사용자 정보/비밀을 포함하지 않는 **안전한 영어 기계 코드 + 한국어 짧은 설명**만 제공. trace는 기본 OFF.

---

## 6. Durable job state machine

```text
created → queued → preflight → running → completed
                          ├── auth_required
                          ├── human_action_required
                          ├── failed
                          ├── cancelled
                          └── uncertain
```

- `idempotency_key`에 Unique constraint. 같은 Telegram update에 동일 작업을 두 번 생성하지 않는다.
- `queued` 시점에서 `provider`, `action`, `conversation_ref`, user text hash, policy decision, creator를 영속 저장한다.
- **송신/클릭 전** `action_attempted_at`과 `pre_action_baseline`(대화 URL, 마지막 대화 marker 등 가능한 최소 근거)을 commit한다.
- 페이지에서 전송이 확인되면 `action_confirmed_at`과 전송 식별 evidence를 기록한다.
- 전송 이후 응답 수신 전에 프로세스가 죽거나 timeout이면 `uncertain` 또는 `result_uncertain`으로 둔다. **같은 질문을 자동 재전송하지 않는다.**
- 완료로 기록하려면 provider별 최소 조건(기존 대화 확인, 대상 일치, 액션 확인, 마지막 응답 완료)을 모두 만족해야 한다. 완료 신호가 불명확하면 `uncertain`.
- 취소는 이미 제출된 웹 질문을 취소/철회하는 게 아니므로 `cancelled`에도 `may_have_side_effects=true` 기록.
- `retry`는 immutable payload로 자동 재실행하지 않는다. 사용자의 수동 상태 확인 후 **새 request ID**와 별도 승인 필요.
- 작업당 제한 시간을 주고 브라우저/페이지가 hung일 때 전체 Telegram gateway를 블로킹하지 않는다.
- 영속 상태와 실제 브라우저 상태 reconciliation을 재시작 시 수행. 과거 `running` job은 완료로 추정하지 않고 `uncertain`으로 복구한다.

### 6.1 Minimal Hermod SQLite schema (proposal)

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL,
  action TEXT NOT NULL,
  conversation_ref TEXT,
  state TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  action_attempted_at TEXT,
  action_confirmed_at TEXT,
  may_have_side_effects INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  result_metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX jobs_status_created ON jobs(state, created_at);
```

- Hermod DB는 **브라우저 작업과 최소 메타데이터만** 보존. 사용자의 질문 본문/ChatGPT 답변 전체 저장을 기본 OFF로 설정.
- 민감한 요청 본문은 프로세스 메모리에서 최소 시간만 유지; persistence가 정말 필요하면 암호화와 보존기간, 위협 모델, 사용자 동의를 먼저 결정.
- 요청 본문 해시만으로 idempotency를 판단하지 않는다. **Heimdall Telegram update ID를 기준**으로 생성한다.
- Hermod의 로컬 DB 백업에는 쿠키/브라우저 프로필을 포함하지 않는다.

---

## 7. Provider Adapter 계약

```python
from typing import Protocol

class BrowserProvider(Protocol):
    name: str

    async def auth_status(self) -> str: ...
    async def open_conversation(self, conversation_ref: str) -> dict: ...
    async def inspect_context(self) -> dict: ...
    async def send_message(self, text: str, *, receipt_id: str) -> dict: ...
    async def wait_for_response(self, *, receipt_id: str, timeout_s: float) -> dict: ...
    async def cancel_operation(self) -> None: ...
```

각 Provider는 아래의 immutable capability declaration으로 기능을 자체 고지한다.

```json
{"provider":"chatgpt","capabilities":{"OPEN":true,"SEARCH":false,"COMPOSE":false,"SUBMIT":false,"COLLECT":false,"READ_HISTORY":false},"status":"manual_handoff_only","reason":"policy_review_required"}
```

```json
{"provider":"local_fixture","capabilities":{"OPEN":true,"SEARCH":true,"COMPOSE":true,"SUBMIT":true,"COLLECT":true,"READ_HISTORY":true},"status":"enabled_for_test"}
```

### 7.1 Browser selectors

- Playwright `get_by_role`, `get_by_label`, `get_by_text`, `get_by_placeholder`처럼 **의미 기반 locator 우선**. 고정 CSS class / 깊은 XPath는 최후의 수단.
- 특정 서비스 DOM의 실제 selector는 **로그인 사용자와 UI 검증 이후에만** 확정. spec에 가상의 ChatGPT selector를 사실처럼 적지 않는다.
- 화면 문구/레이아웃이 달라져 선택 대상이 불분명하면 실패로 처리한다. 화면 여기저기 임의 클릭 금지.
- iframe/여러 탭/모달/배너 등장 시 기대 DOM 계약과 일치하는 경우에만 허용.
- 화면 스크린샷은 디버깅 단계에서 **사용자 명시적 승인 후** 로컬 저장. 기본 영구 로깅 금지.
- UI 변경 감지/버전링: fixture 검증 스냅샷과 provider-specific locator profile version 관리.

### 7.2 Response completion (permitted providers only)

- 제출 전후 페이지 DOM baseline과 현재 대상 대화 id를 비교한다.
- 최종 답변은 **제출한 질문 이후에 새로 생성된 assistant response**만 대상으로 한다.
- 스트리밍 중간 문장은 완료로 오인하지 않는다. provider별 완료 신호 + 짧은 안정화 구간 + deadline으로 판단.
- 긴 출력/복수 assistant 메시지/메뉴·광고·추천 문구 혼입은 분리.
- 다운로드한 첨부/캔버스/이미지/비텍스트 답변은 v1 지원 여부 명확히 `UNSUPPORTED_RESULT` 등으로 기록한다.
- 스크린샷/OCR을 본문 수집 기본 경로로 사용하지 않으며 계정 콘텐츠 무단 수집에 쓰지 않는다.

---

## 8. ChatGPT 통합 정책

### 8.1 기술적 목표와 실제 v1의 경계

**사용자 희망:** Chromium이 `chatgpt.com`에서 이미 로그인된 사용자 계정으로 과거 대화방을 찾고, 그 방에서 새 질문과 답변을 Telegram으로 왕복.

**v1 제공 범위:**

1. 사용자가 공식적으로 내보낸 채팅 기록을 Pi에 수동 제공. Heimdall이 로컬에서 대화 카탈로그 검색.
2. Heimdall이 후보 대화방을 선택하고 사용자에게 관련성/마지막 활동/제목 및 검증된 URL을 안내.
3. Hermod가 프로필에 로그인 여부를 확인하고, 허용된 브라우저 동작으로 해당 대화방까지 탐색.
4. 사용자가 ChatGPT 화면에서 직접 대화 이어가기. Bot은 원문 질문/링크를 함께 안내.
5. ChatGPT의 **무인 자동 Output 추출·회수는 제공하지 않음**. 허용되는 Provider의 자동 왕복은 Hermod가 이미 공통 인터페이스로 지원.

서비스 약관은 OpenAI [Terms of Use](https://openai.com/policies/row-terms-of-use/)에서 직접 확인. 자동 Output 추출을 금지하는 조항이 있으므로, 단순히 브라우저가 로그인됐거나 사용자가 본인 데이터를 소유한다는 이유만으로 이 제약을 무시하지 않는다.

### 8.2 History catalogue

- **Heimdall 책임**: 사용자가 공식 다운로드한 ChatGPT Export ZIP을 사용자가 선택해 import한다. 파일 형식은 변할 수 있으므로 `conversations.json` 존재 여부/구조를 검증하고 없는 경우 명확히 종료.
- 전체 사용자 원본 export는 private import zone에만 두고, ZIP path traversal/zip-bomb/symlink/oversize 보호. 텍스트/개인정보를 git에 기록하지 않는다.
- 각 레코드: `provider`, `title`, `conversation_external_id_if_present`, `verified_url_nullable`, `last_activity`, `local_summary`, `topics`, `import_batch`, `indexed_at`.
- **검증되지 않은 ID로 `https://chatgpt.com/c/<id>` 형태의 링크를 지어내지 않는다.** 웹에 실제 존재하는 링크인지 확인하거나 사용자가 제공한 링크만 verified로 표시.
- export는 snapshot이므로 최신 대화 반영 지연 안내. 자동으로 ChatGPT 웹 전체 대화를 scraping해 맞춰주지 않음.
- 프로젝트 내부 대화와 일반 대화의 구분은 import data가 명시적 정보를 주는 범위 안에서만 추론, 알 수 없으면 unknown.
- 별개 민감 대화(가족/개인·업무)는 사용자 검색 설정에 따른 opt-in filtering. 금융/업무 기밀을 공개 GitHub 이슈에 복사하지 않는다.

---

## 9. Heimdall 통합 / Telegram UX

### 9.1 변화는 기본 OFF

- 기존 일반 문자 전송은 **현재 선택된 Codex 세션으로 가는 동작을 유지**.
- 새 라우터는 `route_mode=off`가 기본. 자동 ChatGPT 전송을 **기본 동작으로 만들지 않는다**.
- `router.on` 후에도 provider capability gate가 ChatGPT `SUBMIT`/`COLLECT`를 금지하면 사용자에게 수동 handoff를 안내한다.
- 라우팅 확신도 경계에 걸리면 후보를 표시하고 주제를 선택하도록 한다. 기존 Codex 스레드의 단일 owner 규칙 유지.
- 새로운 Hermod 잡을 Heimdall의 기존 `jobs` 테이블에 억지로 Codex 세션처럼 저장하지 않는다. `browser_jobs` 별도 테이블 또는 별도 job kind/type migration 설계(백업·레거시 조회 호환 유지).

### 9.2 제안 명령어 (충돌 확인 후 확정)

| Command | Description |
|---|---|
| `/hermod status` | 서비스, 브라우저, 로그인 상태, 지원 capability 요약 |
| `/hermod doctor` | 안전한 진단 작업 예약; 비밀 없는 요약만 반환 |
| `/chat find <질문>` | ChatGPT/Codex 주제별 대화 후보 최대 3개 검색, 모델 호출 없음 |
| `/chat open <후보ID>` | 검증된 ChatGPT URL을 Hermod가 여는 작업, Telegram에 원문 URL도 표시 |
| `/chat route test <질문>` | 실제 전송 없이 목적지 결정과 근거 미리보기 |
| `/chat route on|off` | 라우팅 기능 켜기/끄기. 초기 OFF |
| `/chat status <jobID>` | browser job 상태 확인 |
| `/chat cancel <jobID>` | 실행 중인 browser job 취소 (이미 수행된 동작은 되돌리지 않음) |
| `/chat handoff <후보ID>` | 기존 대화 링크 + 복사 가능한 질문 원문 제공 |

**명령어는 Heimdall owner-private chat에서만 허용**. 기존 명령어와 충돌하면 네이밍 문서화 후 테스트를 우선 진행한다. 비공개 웹 인증 절차를 Telegram 메시지로 요청하지 않는다.

### 9.3 예시 UX

```text
User: 연금 계좌 리밸런싱 얘기 다시 이어서 하자.
Heimdall: 관련 대화 후보
  1) ChatGPT · 연금 포트폴리오 점검 · 신뢰도 높음
  2) Codex · 개인 투자 분석 도구 · 신뢰도 중간
  3) ChatGPT · 잔금 자산 전략 · 신뢰도 중간
  [1번 열기] [2번 Codex 세션 선택] [취소]
User: [1번 열기]
Heimdall: Hermod로 기존 대화 화면을 열었어.
  링크: (검증된 사용자 대화 URL)
  질문을 복사해 해당 화면에서 이어서 입력하면 돼.
```

**장기 UX 목표:** 허가되는 Provider에는 위 마지막 수동 단계 대신 `send/collect`가 작동하고 답변을 Heimdall 기존 Telegram outbox로 전송. 현재 ChatGPT 직접 왕복은 `policy_review_required`로 구분한다.

---

## 10. Security threat model

### 10.1 신뢰 경계

1. Telegram 메시지는 owner check 후에도 **데이터**일 뿐. 임의 브라우저 스크립트로 변환 금지.
2. 웹페이지 콘텐츠는 **untrusted**. 브라우저 DOM 안의 명령/텍스트를 시스템 지시로 실행 금지.
3. 웹 로그인 세션은 **최고 민감정보**. Hermod 서비스 프로세스만 접근 가능.
4. Codex `network` 모드, Heimdall workspace 모드, Hermod 브라우저 권한은 **별개**. 하나가 다른 하나를 자동 승격시키면 안 됨.
5. UDS 로컬이라고 무조건 안전하지 않음. UID/group/메서드 allowlist 검증.

### 10.2 불변 보안 요구

- 사용자의 private browser profile에 `.gitignore`만 의존하지 않기; 파일 권한과 OS UID 격리.
- shell history, journal, stderr, GitHub Actions, PR 로그, Telegram에 세션·쿠키·기밀 질문 원문 유출 금지.
- Playwright trace/HAR/network body logging 기본 금지. 진단 artifact는 opt-in, 마스킹/짧은 보존기간.
- `--remote-debugging-port=0.0.0.0:*` 금지. 꼭 필요한 개발 CDP도 127.0.0.1/SSH tunnel로 한정하고 운영 중 종료.
- HTTPS 인증서 경고 무시/보안 경고 클릭 자동화 금지.
- browser에서 받은 파일 자동 실행/쉘 연계 금지.
- 브라우저 작업은 소유자가 명시적으로 허용한 provider, domain, operation에 한정.
- fixture 테스트에서 `submit` 고의 중복을 만들어도 실제 전송은 단 한 번 이뤄지는지 검증.
- 중요한 실제 계정 변경 조작은 새로운 승인 설계 이전까지 전부 금지.
- `danger-full-access`, `--no-sandbox`, root 실행을 일반 운영 기본값으로 정하지 말 것.

### 10.3 리소스 제한

- Pi 4GB에서 Chromium은 상대적으로 무거움. 운영 전 **실측** RSS/CPU/실행시간 기록.
- 동시 브라우저 작업 수 `1`; 초과 요청은 작은 영속 큐로 보내고 빠르게 응답.
- 예시 제안: queue 10개, browser job total deadline 120초, 사이트 navigation 30초, idle close 10분. **이 수치는 초기 설정안이지 관측한 성능이 아니다.** 실제 smoke 후 수정 가능.
- 전역 disk-space guard; 첨부/다운로드 기본 차단; profile 비정상 증가 관측 시 alert.
- 추적용 screenshots, traces는 기본 없음. 테스트에서 명시 승인 시만 사용하고 개인자료를 제외해 자동 정리.
- systemd cgroup memory controller가 Pi에서 미구현 상태였다는 기존 기록이 있으므로 MemoryMax만 믿지 말고 프로세스 관측/자체 soft-limit/health check 적용.

---

## 11. Logging / metrics / 운영

### 11.1 구조화된 비밀 없는 기록

필수 로그 필드: `timestamp`, `request_id`, `job_id`, `action`, `provider`, `state`, `duration_ms`, `error_code`, `profile_version`, `ui_adapter_version`.

미기록 필드: 브라우저 쿠키, Authorization 헤더, 전체 질문/응답, 비밀번호, 복구 코드, 원본 private URL의 sensitive query, 웹 DOM dump.

메트릭: 요청 성공률, navigation 실패율, auth-expired 수, UI_CHANGED 수, uncertain 수, 작업별 latency, idle browser RSS, queue depth, 소켓 연결 에러.

### 11.2 필요 운영 명령 예시

```bash
sudo systemctl status hermod.service --no-pager
sudo journalctl -u hermod.service -n 50 --no-pager
sudo systemctl restart hermod.service  # 배포 절차에 따라 수동 실행
```

Hermod 재시작은 Heimdall 및 Kakao-Radar 재시작을 수반하지 않아야 한다. 부팅 자동 시작/재시작은 실제 운영 테스트 성공 후 승인받아 활성화한다. 상태가 불명확한 브라우저 작업은 무인 자동 재생 금지.

### 11.3 Backup & cleanup

- Hermod source/config **비밀 없는 부분만** GitHub에 보관.
- Hermod job ledger는 필요한 최소 기간 보존. 기본 TTL 설정 및 cleanup dry-run 우선.
- 브라우저 로그인 프로필은 기본 백업 제외, 인증 만료 시 사용자 재로그인을 통한 복구를 선택.
- Heimdall의 기존 `/backup`에 Hermod 프로필을 암묵적으로 집어넣지 않는다.
- 로컬 ChatGPT 공식 export도 기본 전체 백업/자동 공유 금지. import 정책은 Heimdall의 Knowledge/개인정보 보존계획과 연결.

---

## 12. 단계별 구현 PR / acceptance criteria

### PR-0: Read-only feasibility & threat model

- 두 repo의 현재 HEAD/브랜치와 기존 Heimdall 서비스 설정 확인.
- `doctor`로 Chromium/Playwright 설치 경로와 ARM64 동작 검증.
- local fixture HTML에서 launch/click/screenshot(민감정보 없음) smoke.
- 사용자의 현재 Pi에서 systemd 보안 옵션, UID/그룹, 리소스 방안 검증.
- `docs/THREAT_MODEL.md`, `docs/DECISIONS.md`에 결정 기록.
- **실제 ChatGPT 로그인 또는 전송·회수는 수행하지 않음.**

**Done:** OS/패키지/격리 진단 결과와 재현 가능한 smoke 코드, 중요한 블로커 목록이 모두 문서화됨.

### PR-1: Hermod standalone daemon + UDS

- 새로운 `hermod` 독립 패키지, `pyproject`, systemd unit, socket permission, config parser, DB migrations.
- `system.health`, `browser.status`, `jobs.create/get/cancel`, idempotent transitions 구현.
- 작동하는 UDS mock client 및 단일 브라우저 매니저.
- browser launch 없이도 RPC health와 crash recovery 테스트.

**Done:** 서비스 독립 기동/종료, UID 허용/거부, duplicate request 단일 job, crash 이후 uncertain 정합성, 비밀 무로그 테스트 통과.

### PR-2: Generic fixture conversation driver

- 완전히 오프라인/local fixture 웹앱: list, search, thread open, compose, send, streaming, finish, interrupted, simulated login.
- `BrowserProvider` + `FixtureProvider`, 해당 provider 한정 `SUBMIT`·`COLLECT` 허용.
- locator/versioned error 처리, duration/cancel/uncertain/중복 메시지 안전장치 구현.

**Done:** fixture에 실제 질문을 1회 보내고 예상 응답을 1회 수신; timeout/재시작/DOM 변경/인증 요구/중복 재전송 금지 회귀 통과.

### PR-3: ChatGPT read-only navigation + manual handoff

- Hermod에 `ChatGPTProvider` 추가, 기본 capability는 `OPEN`만 활성.
- owner 수동 로그인 워크플로. 로그인 상태는 브라우저 UI에서 최소 메타데이터로 확인, cookie export 금지.
- 사전 **검증된** conversation reference만 navigation; 검증 불가면 URL 추측 없이 `PAGE_MISMATCH`.
- ChatGPT 메시지 자동 전송·Output 수집 기능은 미실행 및 명시적 disabled.

**Done:** 로그인 미실행, 로그인 필요, 수동 로그인 완료, 검증 URL 열기, UI 변경 시 fail-closed 상태를 각각 테스트. 계정 정책을 위반하는 크롤링/추출 시험 금지.

### PR-4: Heimdall integration

- Heimdall에 `HermodClient`(UDS)와 새 `browser_jobs` 타입/테이블 또는 호환 migration.
- `/hermod status`, `/chat find`, `/chat open`, `/chat route test`, `/chat handoff` 등 최소 명령 추가.
- ChatGPT 공식 export import는 Heimdall 별도 모듈; 순수 로컬 parser와 검색만 작동.
- routing 기본 OFF, Codex 기존 세션 메시지 경로 변화 없음.
- owner-only, durable pending, idempotency, existing outbox와 rollback 연동.

**Done:** Telegram mock→Heimdall→UDS Hermod→fixture→Heimdall outbox roundtrip, 기존 Codex/Knowledge/이미지 테스트 전부 통과. ChatGPT는 manual handoff까지.

### PR-5: Optional future permitted-provider automation

- 서비스 약관 및 사용자 승인 등 허용 요건 충족한 Provider에만 `COMPOSE`, `SUBMIT`, `COLLECT` capability 켜기.
- per-provider 전송 후 중복/불확실 복구 정책 검증.
- ChatGPT 자동 Output 추출 기능은 현재 약관 제한 때문에 **사용 가능 상태라고 보고하지 말 것**.

**Done:** 허용된 서비스에서만 실제 자동 왕복이 검증되며 ChatGPT provider는 정책 변경/확인 없는 한 비활성 상태 유지.

---

## 13. Test matrix (minimum)

| 구분 | 시나리오 | 기대 동작 |
|---|---|---|
| Auth | 다른 UID가 UDS 접근 | RPC 거절 |
| Auth | ChatGPT 미로그인/MFA | `AUTH_REQUIRED` / `HUMAN_ACTION_REQUIRED`; 안전 종료 |
| Scope | 부적절한 임의 URL 입력 | `FORBIDDEN`; 브라우저 미탐색 |
| Scope | ChatGPT에 submit/collect 요청 | `POLICY_REVIEW_REQUIRED`; 실제 DOM action 없음 |
| Function | fixture conversation 찾기 | 정확한 대상만 선택 |
| Function | fixture 한 건 send/collect | 정확한 메시지 한 건, 완료 결과 한 건 |
| Replay | 동일 idempotency_key 두 번 | 하나의 job만 생성 |
| Replay | send 뒤 crash | `uncertain`, 자동 재전송 없음 |
| Recovery | 브라우저 죽음 / systemd restart | 재로그인 필요 여부/unknown 분리 |
| UI | locator 변경 / 중복 요소 | `UI_CHANGED` 또는 `PAGE_MISMATCH`, 임의 클릭 없음 |
| Timeout | 답변 120초 넘음 | 강제 완료 추정 금지 |
| Context | Codex 현재 selected thread | 원래 동작 보존 |
| Context | Auto-Memory ON/OFF | Hermod 독립·회귀 없음 |
| Privacy | trace/journal/DB | 비밀번호·쿠키·질문·답변 본문 노출 없음 |
| Resource | 복수 요청 10개 | 동시 1개, bounded queue; Pi 과부하 없음 |
| Router | 낮은 라우팅 확신도 | 후보 추천, 자동 전송 안 함 |
| Handoff | ChatGPT export에 URL 미확인 | URL 추정 금지, 사용자 링크 확인 요청 |
| Ops | Hermod stopped | Heimdall Codex 경로 영향 없이 오류 알림 |
| Ops | Kakao-Radar 상태 | 배포 전후 변경 없음 |

테스트는 **unit → fake provider → localhost browser smoke → Heimdall 통합 fake Telegram → 실제 Pi 리소스 smoke** 순서로 진행. 실제 로그인이나 ChatGPT 계정 조작은 별도 사용자 참여 승인 후.

---

## 14. 제약/의사결정/열린 질문

1. **ChatGPT 자동 송수신 허용성:** 핵심 운영 제약. v1 disabled. 디자인 완성도를 이유로 몰래 기능 활성화 금지.
2. **Pi headless manual login:** GUI 접근 방식 결정 필요. 우선 비공개 localhost 환경에서 안전한 방법을 탐색하고 소유자에게 선택지 보고.
3. **Browser profile과 systemd hardening:** 소켓 그룹, bubblewrap/namespace 충돌, Chromium sandbox를 실제 환경으로 확인.
4. **ChatGPT conversation URL provenance:** 공식 export에 URL이 없거나 달라질 수 있음. 확정 가능한 대화만 deep link로 연결.
5. **Router confidence:** 초기 keyword/FTS5 우선, LLM 호출 없는 기본 경로. 라우팅 성능은 별도 평가 데이터로 확인.
6. **메시지 내용 보존:** v1에서 Hermod는 전체 body 저장 금지; 부분 실패 후 정확한 수동 확인 UX는 Heimdall 쪽에 구축.
7. **시스템 계정/저장 위치/서비스 부팅 설정:** 설치 스크립트가 임의로 sudo 변경하는 대신 사용자 승인 절차를 분명히 한다.

---

## 15. Codex handoff prompt (복사해 실행)

> 아래 요청을 Codex CLI에 제공한다. Codex가 이 문서를 읽을 수 있는 로컬 경로에 먼저 둔다.

```text
You are implementing a new independent project named HERMOD, a secure browser controller called by my existing Heimdall Telegram bridge.

Read the attached HERMOD_BROWSER_CONTROLLER_SPEC_v1.0.md completely and treat it as the primary design contract. Existing Heimdall is in /home/haaland/heimdall (GitHub exwaiz/heimdall, main). Do not assume old docs describe current source. Inspect actual source and installed environment before choosing integration points.

Primary priorities:
1. Preserve existing Heimdall/Codex sessions, Auto-Memory, credentials, backups, Kakao-Radar and systemd services. Do not modify or restart them without explicit approval.
2. Implement Hermod as a separate Python repository/package/service, not a Codex tool that is called on every question.
3. Keep browser credentials exclusively in a separate OS-identity-controlled private profile. Heimdall uses a versioned Unix socket RPC client and never receives cookies or storage state.
4. Implement phases PR-0 and PR-1 first, with a fully local browser fixture to test navigation and system constraints. Then PR-2. Do not perform account login or real remote web mutations during tests.
5. For ChatGPT specifically: the end vision is to return to existing user conversations, but consumer terms prohibit automated extraction of data/Output. Therefore ship ChatGPT provider in open/manual-handoff mode only until explicitly permitted. Implement full send/receive for local fixtures or other permitted services, never behind an undocumented API or CAPTCHA bypass.
6. Reuse Heimdall's current durable job and outbox design principles. Keep browser jobs separate from Codex thread jobs, make side effects idempotent, and never replay uncertain submissions automatically.
7. Use deterministic Python and SQLite for routine operations. Never spend Codex inference calls on each browser operation or simple routing.
8. Deliver source code, example configuration, systemd unit, tests, security model, operations docs, a concrete architecture decision log, and a detailed smoke report.

Execution order:
A. Print a concise gap analysis vs the spec, exact installed package/browser versions, checked user/service permissions, Pi resource limits. Distinguish observed facts from assumptions.
B. Propose a small PR/commit breakdown and identify any privileged/manual-login steps needing my approval.
C. Implement PR-0/PR-1, run unit and local fixture tests; fix failures. Do not modify existing Heimdall production service.
D. Implement PR-2 local fixture end-to-end and report actual measurements.
E. Create the Heimdall integration adapter (PR-4) behind default-OFF config only after the Hermod contract is tested. Update existing tests and add compatibility tests.
F. Generate final deliverable: git diff/commits, tests passed/failed/skipped, security audit, paths, exact manual deployment/login steps, known limitations and rollback instructions.

If a task is blocked by GitHub permissions, systemd privilege or manual account login, preserve working code and report the blocker rather than guessing success or bypassing protection.
```

---

## 16. 소스 / 기술 참고 (검증 시점: 2026-10-17)

- Heimdall `main` README: https://github.com/exwaiz/heimdall/blob/main/README.md
- Heimdall Auto-Memory: https://github.com/exwaiz/heimdall/blob/main/docs/AUTO_MEMORY_IMPLEMENTATION.md
- Heimdall Temporary Access / Playwright smoke: https://github.com/exwaiz/heimdall/blob/main/docs/TEMPORARY_ACCESS.md
- Heimdall Security: https://github.com/exwaiz/heimdall/blob/main/SECURITY.md
- Playwright Python browser persistent context: https://playwright.dev/python/docs/api/class-browsertype
- Playwright Python authentication and secret state warnings: https://playwright.dev/python/docs/auth
- Playwright Python robust locators: https://playwright.dev/python/docs/locators
- ChatGPT official data export: https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data
- OpenAI consumer Terms of Use: https://openai.com/policies/row-terms-of-use/

**주의:** 기술 문서와 정책은 바뀔 수 있다. 해당 날짜에 확인된 내용과 실제 실행 시점의 내용을 구분한다. GitHub 위키/README는 과거 스모크 결과이지 현재 Pi가 무조건 같은 상태라는 증거가 아니다.

---

## 17. Final acceptance checklist

- [ ] `hermod` 독립 repo/code/package 준비
- [ ] Pi의 Playwright/Chromium 실제 실행 진단 성공
- [ ] browser profile 별도 UID로 격리, cookie leakage 검사 통과
- [ ] UDS RPC peer/permission/size/version validation 통과
- [ ] SQLite idempotent queue 및 uncertain crash recovery 통과
- [ ] fixture `open → compose → send → response → complete` E2E 성공
- [ ] ChatGPT provider `OPEN` handoff만 가능하고 `SUBMIT/COLLECT`는 policy gate 차단
- [ ] Heimdall Auto-Memory/기존 Codex 동작 회귀 테스트 통과
- [ ] Kakao-Radar 관련 서비스 파일/상태 변동 없음
- [ ] Telegram owner-only `/hermod`, `/chat` 신규 명령 검증
- [ ] Test log/token/screenshot/export/profile 자료 유출 없음
- [ ] systemd 독립 시작/중지, 롤백 절차 완성
- [ ] UI 변경·MFA·중복 전송·시간초과 시 fail-closed 검증
- [ ] 사용자가 승인하기 전 실제 ChatGPT 로그인/서비스 자동화·운영 배포 미실행

**한 문장 목표:** *Heimdall은 적절한 대화방을 결정하고, Hermod는 보호된 브라우저에서 허가된 웹 작업을 정확히 수행한다.*
