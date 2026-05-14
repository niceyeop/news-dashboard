# Oracle 서버 자동 배포 가이드

## 목표
- `main` 브랜치에 push하면 Oracle 서버로 자동 배포
- 최신 코드 반영 후 `news-dashboard` 서비스 자동 재시작

## 1. Oracle 서버 1회 초기 설정

서버에서 저장소를 한 번 클론한 뒤 아래 실행:

```bash
sudo bash scripts/setup_oracle_server.sh ubuntu /opt/news-dashboard
```

- `ubuntu`: 배포에 사용할 SSH 사용자
- `/opt/news-dashboard`: 서버 앱 경로

이 스크립트가 자동으로 처리하는 내용:
- 필수 패키지 설치 (`git`, `python3-venv` 등)
- 앱 디렉터리 생성/권한 설정
- `news-dashboard.service` 등록
- GitHub Actions SSH 사용자에게 `systemctl` 재시작 권한 부여

## 2. 서버 환경변수 파일 생성

서버에서 아래 파일 생성:

`/opt/news-dashboard/.env`

예시:

```bash
GEMINI_API_KEY=your_key
NEWS_DASHBOARD_CACHE_DIR=/opt/news-dashboard/.news_dashboard_cache
```

## 3. GitHub Actions Secrets 등록

저장소 경로:
- `Settings > Secrets and variables > Actions`

필수 시크릿:
- `ORACLE_HOST`: 서버 공인 IP 또는 도메인
- `ORACLE_USER`: SSH 사용자 (예: `ubuntu`)
- `ORACLE_PORT`: SSH 포트 (기본 `22`)
- `ORACLE_SSH_PRIVATE_KEY`: 배포용 개인키 전체 내용
- `APP_DIR`: 서버 앱 경로 (예: `/opt/news-dashboard`)

## 4. 배포 동작

- 트리거: `main` push 또는 수동 실행(workflow_dispatch)
- 워크플로: `.github/workflows/deploy-oracle.yml`
- 서버 실행 스크립트: `scripts/deploy.sh`

`deploy.sh` 처리 순서:
- 최신 코드 fetch/reset
- `.venv` 생성(없으면)
- 의존성 설치
- `news-dashboard.service` 재시작

## 5. 배포 확인

서버에서:

```bash
sudo systemctl status news-dashboard.service
journalctl -u news-dashboard.service -f
```

브라우저:

- `http://<ORACLE_HOST>:8501`
