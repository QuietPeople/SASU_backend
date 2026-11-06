데모 파일 적용법

영상은 demo_seeds/videos, 영상별 첫 프레임 썸네일은 demo_seeds/thumbnails에 포함되어 있음.
파일 이름과 내용을 유지한 상태로 아래 명령 실행.
현재 원본 영상·썸네일은 각각 31개이며, seed.sql에 정의한 콘텐츠 25개를 DB에 등록함.

# 1. 최신 내용 받기
git pull origin main

# 2. 전체 데모를 초기화할 경우에만 기존 DB·영상·썸네일 볼륨 삭제
# 기존 데이터를 유지할 경우 이 단계 생략. demo_seeds의 원본 파일은 유지됨.
docker compose down -v

# 3. 컨테이너 빌드·실행
docker compose up --build -d --wait

# 4. DB 구조 생성
docker compose exec backend alembic upgrade head

# 5. 데모 데이터 삽입
docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro backend python -m demo_seeds.demo_injection

# 6. '데모 seed 처리 완료' 메시지가 출력되면 성공

재실행 시 기존 데이터는 유지하고, 기존 데모 콘텐츠에 썸네일이 없으면 추가함.
직접 등록한 썸네일이나 교체한 영상은 덮어쓰지 않음.
시리즈용 이미지는 별도로 만들지 않으며, 각 시리즈의 첫 영상 썸네일을 사용함.
