import os
import random
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "motel_db"),
    user=os.getenv("DB_USER", "Jonny-Pak"),
    password=os.getenv("DB_PASSWORD", "190705"),
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=os.getenv("DB_PORT", "5432")
)
cursor = conn.cursor()

provinces = [
    {"name": "TP. Hồ Chí Minh", "lat": 10.7769, "lng": 106.7009, "districts": ["Quận 1", "Quận 3", "Quận 10", "Quận Bình Thạnh", "Quận Gò Vấp", "TP. Thủ Đức", "Quận 7"], "streets": ["Nguyễn Thị Minh Khai", "Cách Mạng Tháng 8", "Xô Viết Nghệ Tĩnh", "Phan Văn Trị", "Đia Biên Phủ", "Lê Văn Việt", "Nguyễn Văn Linh"]},
    {"name": "Hà Nội", "lat": 21.0285, "lng": 105.8542, "districts": ["Quận Cầu Giấy", "Quận Đống Đa", "Quận Ba Đình", "Quận Thanh Xuân", "Quận Hai Bà Trưng", "Quận Hà Đông"], "streets": ["Chùa Láng", "Xuân Thủy", "Thái Hà", "Nguyễn Trãi", "Trần Đại Nghĩa", "Lê Văn Lương"]},
    {"name": "Đà Nẵng", "lat": 16.0544, "lng": 108.2022, "districts": ["Quận Hải Châu", "Quận Thanh Khê", "Quận Sơn Trà", "Quận Ngũ Hành Sơn", "Quận Liên Chiểu"], "streets": ["Nguyễn Văn Linh", "Lê Duẩn", "Phạm Văn Đồng", "Ngũ Hành Sơn", "Ton Đức Thắng"]},
    {"name": "Hải Phòng", "lat": 20.8449, "lng": 106.6881, "districts": ["Quận Ngô Quyền", "Quận Lê Chân", "Quận Hồng Bàng", "Quận Hải An"], "streets": ["Lạch Tray", "Tô Hiệu", "Điện Biên Phủ", "Lê Hồng Phong"]},
    {"name": "Cần Thơ", "lat": 10.0452, "lng": 105.7469, "districts": ["Quận Ninh Kiều", "Quận Bình Thủy", "Quận Cái Răng"], "streets": ["3 Tháng 2", "Nguyễn Văn Cừ", "Trần Hưng Đạo", "Mậu Thân"]},
    {"name": "Bình Dương", "lat": 10.9804, "lng": 106.6519, "districts": ["TP. Thủ Dầu Một", "TP. Dĩ An", "TP. Thuận An"], "streets": ["Đại lộ Bình Dương", "Yersin", "GS1", "22 Tháng 12"]},
    {"name": "Đồng Nai", "lat": 10.9574, "lng": 106.8427, "districts": ["TP. Biên Hòa", "Huyện Long Thành", "TP. Long Khánh"], "streets": ["Phạm Van Thuận", "Đồng Khởi", "Nguyễn Ái Quốc", "Võ Thị Sáu"]},
    {"name": "Bà Rịa - Vũng Tàu", "lat": 10.3460, "lng": 107.0843, "districts": ["TP. Vũng Tàu", "TP. Bà Rịa"], "streets": ["Thùy Vân", "Lê Hồng Phong", "Ba Cu", "Nguyễn Thái Học"]},
    {"name": "Khánh Hòa", "lat": 12.2388, "lng": 109.1967, "districts": ["TP. Nha Trang", "TP. Cam Ranh"], "streets": ["Trần Phú", "Hung Vương", "Nguyễn Thiện Thuật", "Lê Thánh Tôn"]},
    {"name": "Lâm Đồng", "lat": 11.9404, "lng": 108.4583, "districts": ["TP. Đà Lạt", "TP. Bảo Lộc"], "streets": ["Phan Đình Phùng", "Bùi Thị Xuân", "Hai Bà Trưng", "Phù Đổng Thiên Vương"]},
    {"name": "Thừa Thiên Huế", "lat": 16.4637, "lng": 107.5909, "districts": ["TP. Huế"], "streets": ["Lê Lợi", "Hùng Vương", "Bà Triệu", "Nguyễn Huệ"]},
    {"name": "Quảng Nam", "lat": 15.5658, "lng": 108.4812, "districts": ["TP. Tam Kỳ", "TP. Hội An"], "streets": ["Hùng Vương", "Phan Châu Trinh", "Cửa Đại", "Lý Thường Kiệt"]},
    {"name": "Bình Định", "lat": 13.7830, "lng": 109.2197, "districts": ["TP. Quy Nhơn"], "streets": ["An Dương Vương", "Nguyễn Tất Thành", "Spring Xuân Diệu", "Lê Hồng Phong"]},
    {"name": "Phú Yên", "lat": 13.0880, "lng": 109.3082, "districts": ["TP. Tuy Hòa"], "streets": ["Hùng Vương", "Độc Lập", "Trần Hưng Đạo", "Lê Lợi"]},
    {"name": "Bình Thuận", "lat": 10.9289, "lng": 108.1021, "districts": ["TP. Phan Thiết"], "streets": ["Thủ Khoa Huân", "Nguyễn Tất Thành", "Tôn Đức Thắng"]},
    {"name": "Nghệ An", "lat": 18.6796, "lng": 105.6813, "districts": ["TP. Vinh"], "streets": ["Lê Duẩn", "Nguyễn Thị Minh Khai", "Quang Trung"]},
    {"name": "Thanh Hóa", "lat": 19.8075, "lng": 105.7764, "districts": ["TP. Thanh Hóa"], "streets": ["Trần Phú", "Lê Hoàn", "Quang Trung", "Bà Triệu"]},
    {"name": "Quảng Ninh", "lat": 20.9599, "lng": 107.0448, "districts": ["TP. Hạ Long", "TP. Cẩm Phả"], "streets": ["Hạ Long", "Cái Dăm", "Nguyễn Văn Cừ", "Lê Thánh Tông"]},
    {"name": "Thái Nguyên", "lat": 21.5942, "lng": 105.8482, "districts": ["TP. Thái Nguyên"], "streets": ["Lương Ngọc Quyến", "Hoàng Văn Thụ", "Z115", "Thống Nhất"]},
    {"name": "Bắc Ninh", "lat": 21.1861, "lng": 106.0763, "districts": ["TP. Bắc Ninh", "TP. Từ Sơn"], "streets": ["Lý Thái Tổ", "Nguyễn Gia Thiều", "Trần Hưng Đạo"]},
    {"name": "Bắc Giang", "lat": 21.2731, "lng": 106.1946, "districts": ["TP. Bắc Giang"], "streets": ["Xương Giang", "Hoàng Văn Thụ", "Nguyễn Thị Lưu"]},
    {"name": "Vĩnh Phúc", "lat": 21.3093, "lng": 105.5969, "districts": ["TP. Vĩnh Yên", "TP. Phúc Yên"], "streets": ["Mê Linh", "Tôn Đức Thắng", "Hùng Vương"]},
    {"name": "Hải Dương", "lat": 20.9380, "lng": 106.3304, "districts": ["TP. Hải Dương"], "streets": ["Trần Hưng Đạo", "Thanh Niên", "Nguyễn Lương Bằng"]},
    {"name": "Hưng Yên", "lat": 20.6464, "lng": 106.0511, "districts": ["TP. Hưng Yên", "Huyện Văn Giang"], "streets": ["Điện Biên Phủ", "Ecopark", "Nguyễn Văn Linh"]},
    {"name": "Nam Định", "lat": 20.4371, "lng": 106.1685, "districts": ["TP. Nam Định"], "streets": ["Trần Hưng Đạo", "Lê Hồng Phong", "Hùng Vương"]},
    {"name": "Kiên Giang", "lat": 10.0125, "lng": 105.0809, "districts": ["TP. Rạch Giá", "TP. Phú Quốc"], "streets": ["Nguyễn Trung Trực", "Trần Phú", "Trần Hưng Đạo"]},
    {"name": "An Giang", "lat": 10.3800, "lng": 105.4328, "districts": ["TP. Long Xuyên", "TP. Châu Đốc"], "streets": ["Trần Hưng Đạo", "Hà Hoàng Hổ", "Lê Lợi"]},
    {"name": "Tiền Giang", "lat": 10.3542, "lng": 106.3653, "districts": ["TP. Mỹ Tho"], "streets": ["Ấp Bắc", "Lê Thị Hồng Gấm", "Nam Kỳ Khởi Nghĩa"]},
    {"name": "Long An", "lat": 10.5333, "lng": 106.4167, "districts": ["TP. Tân An", "Huyện Đức Hòa"], "streets": ["Hùng Vương", "Nguyễn Đình Chiểu", "Quốc Lộ 1A"]},
    {"name": "Tây Ninh", "lat": 11.3115, "lng": 106.0984, "districts": ["TP. Tây Ninh", "Thị xã Hòa Thành"], "streets": ["Cách Mạng Tháng 8", "30 Tháng 4", "Long Hoa"]},
    {"name": "Đắk Lắk", "lat": 12.6667, "lng": 108.0500, "districts": ["TP. Buôn Ma Thuột"], "streets": ["Lê Duẩn", "Phan Chu Trinh", "Nguyễn Tất Thành", "Mai Hắc Đế"]},
    {"name": "Gia Lai", "lat": 13.9833, "lng": 108.0000, "districts": ["TP. Pleiku"], "streets": ["Hùng Vương", "Phan Đình Phùng", "Lê Lợi", "Nguyễn Tất Thành"]}
]

phone_prefixes = ["090", "091", "093", "094", "096", "097", "098", "086", "088", "089", "033", "034", "035", "036", "037", "038", "039", "070", "079", "077", "076", "078", "058", "059"]

room_adjectives = ["mới xây cao cấp", "giá rẻ đầy đủ tiện nghi", "sạch đẹp yên tĩnh", "an ninh có ban công", "gần chợ thoáng mát", "khép kín giờ giấc tự do", "có gác lửng thang máy", "trang bị full nội thất"]
house_adjectives = ["nguyên căn hẻm xe hơi", "1 trệt 2 lầu rộng rãi", "mặt tiền kinh doanh tốt", "thiết kế hiện đại sân vườn", "4 phòng ngủ full nội thất", "nguyên căn mới sửa sang sạch sẽ", "khu dân cư an ninh biệt lập"]

inserted_count = 0

for p in provinces:
    p_name = p["name"]
    base_lat = p["lat"]
    base_lng = p["lng"]
    districts = p["districts"]
    streets = p["streets"]
    
    # 5 Phòng trọ (phong_tro)
    for i in range(1, 6):
        house_no = random.randint(1, 499)
        street = random.choice(streets)
        district = random.choice(districts)
        adj = random.choice(room_adjectives)
        
        address = f"Số {house_no} đường {street}, {district}, {p_name}"
        # Price for rooms: 1.2M - 4.5M VND
        price = random.randrange(1200000, 4500000, 100000)
        phone = random.choice(phone_prefixes) + f"{random.randint(1000000, 9999999)}"
        
        # Small random coordinate offset (±0.03 deg is roughly ~3 km around province center)
        lat = round(base_lat + random.uniform(-0.035, 0.035), 6)
        lng = round(base_lng + random.uniform(-0.035, 0.035), 6)
        
        query = """
            INSERT INTO motel_rooms (address, price, phone, property_type, expires_at, is_active, geom)
            VALUES (%s, %s, %s, 'phong_tro', NOW() + INTERVAL '30 days', TRUE, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """
        cursor.execute(query, (address, price, phone, lng, lat))
        inserted_count += 1

    # 5 Nhà nguyên căn (nha_nguyen_can)
    for i in range(1, 6):
        house_no = random.randint(1, 499)
        street = random.choice(streets)
        district = random.choice(districts)
        adj = random.choice(house_adjectives)
        
        address = f"Nhà số {house_no} đường {street}, {district}, {p_name}"
        # Price for houses: 5.5M - 25M VND
        price = random.randrange(5500000, 25000000, 500000)
        phone = random.choice(phone_prefixes) + f"{random.randint(1000000, 9999999)}"
        
        lat = round(base_lat + random.uniform(-0.035, 0.035), 6)
        lng = round(base_lng + random.uniform(-0.035, 0.035), 6)
        
        query = """
            INSERT INTO motel_rooms (address, price, phone, property_type, expires_at, is_active, geom)
            VALUES (%s, %s, %s, 'nha_nguyen_can', NOW() + INTERVAL '30 days', TRUE, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """
        cursor.execute(query, (address, price, phone, lng, lat))
        inserted_count += 1

conn.commit()
cursor.close()
conn.close()
print(f"SUCCESS: Inserted {inserted_count} sample records across {len(provinces)} provinces in Vietnam!")
