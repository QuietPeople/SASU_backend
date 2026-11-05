데모 파일 적용법

demo_seeds/videos에 구글드라이브에서 내려받은 영상을 삽입(csv는 제외)

# 1. 최신 내용 받기
git pull origin main

# 2. 전체 데모를 초기화할 경우에만 기존 DB·영상·썸네일 볼륨 삭제
# 기존 데이터를 유지할 경우 이 단계 생략. 원본 demo_seeds/videos는 유지됨.
docker compose down -v

# 3. 컨테이너 빌드·실행
docker compose up --build -d --wait

# 4. DB 구조 생성
docker compose exec backend alembic upgrade head

# 5. 데모 데이터 삽입
docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro backend python -m demo_seeds.demo_injection

# 6. '데모 seed 처리 완료' 메시지가 출력되면 성공