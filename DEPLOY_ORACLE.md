# Oracle 자동 배포/실행 설정

## 1) 오라클 서버 1회 초기 설정

1. 서버에 기본 패키지 설치
   - `sudo apt update && sudo apt install -y git python3 python3-venv python3-pip`
2. 앱 디렉터리 생성
   - `sudo mkdir -p /opt/news-dashboard`
   - `sudo chown -R $USER:$USER /opt/news-dashboard`
3. systemd 서비스 등록
   - `sudo cp infra/news-dashboard.service /etc/systemd/system/news-dashboard.service`
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable news-dashboard.service`
4. 서비스 파일 경로/사용자 확인
   - `infra/news-dashboard.service` 안의 `User`, `WorkingDirectory`, `EnvironmentFile`, `ExecStart`를 서버 환경과 맞추기

## 2) 서버 환경변수 파일 생성

`/opt/news-dashboard/.env` 파일 생성:

```bash
GEMINI_API_KEY=your_key
NEWS_DASHBOARD_CACHE_DIR=/opt/news-dashboard/.news_dashboard_cache
```

필요한 키가 더 있으면 같은 파일에 추가하면 됩니다.

## 3) GitHub Actions 시크릿 등록 (Repository > Settings > Secrets and variables > Actions)

- `ORACLE_HOST`: 오라클 서버 공인 IP 또는 도메인
- `ORACLE_USER`: SSH 사용자명 (예: `ubuntu`)
- `ORACLE_PORT`: SSH 포트 (기본 `22`)
- `ORACLE_SSH_PRIVATE_KEY`: 배포용 개인키 전체 내용
- `APP_DIR`: 서버 배포 경로 (예: `/opt/news-dashboard`)

## 4) 자동 배포 동작

- `main` 브랜치에 push하면 `.github/workflows/deploy-oracle.yml`가 실행됩니다.
- 워크플로가 SSH로 서버에 접속해 `scripts/deploy.sh`를 실행합니다.
- 배포 스크립트는 아래를 수행합니다.
  - 최신 코드 동기화
  - 가상환경/의존성 설치
  - `news-dashboard.service` 재시작

## 5) 확인 방법

서버에서:

```bash
sudo systemctl status news-dashboard.service
journalctl -u news-dashboard.service -f
```

브라우저에서:

- `http://<ORACLE_HOST>:8501`
