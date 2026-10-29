데모 파일 적용법

demo_seeds/videos에 구글드라이브에서 내려받은 영상을 삽입(csv는 제외)

# 1. 최신 내용 받기
git pull origin main

# 2. DB에 기존 데이터가 있다면 삭제 권장, storage/videos 아래 파일들도 삭제

# 3. 컨테이너 빌드·실행
docker compose up --build -d --wait

# 4. DB 구조 생성
docker compose exec backend alembic upgrade head

# 5. 데모 데이터 삽입
docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro backend python -m demo_seeds.demo_injection

# 6. '데모 seed 처리 완료' 메시지가 출력되면 성공