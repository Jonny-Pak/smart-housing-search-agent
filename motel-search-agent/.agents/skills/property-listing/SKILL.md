name: property-listing
description: Sử dụng khi người dùng có nhu cầu đăng tin, ký gửi cho thuê phòng trọ hoặc nhà nguyên căn.

# Workflow
1. Phân tích yêu cầu của người dùng để trích xuất 3 thông tin bắt buộc: Địa chỉ (address), Giá thuê (price - chuyển sang số nguyên) và Số điện thoại liên hệ (phone).
2. Kiểm tra tính hợp lệ của dữ liệu đầu vào: Giá thuê phải là số dương (> 0, không được là giá âm), Số điện thoại phải đúng chuẩn Việt Nam (bắt đầu bằng số 0, gồm đúng 10 chữ số). Nếu thiếu hoặc sai thông tin, BẮT BUỘC KHÔNG đăng tin và yêu cầu người dùng nhập lại cho đúng bằng ngôn ngữ tự nhiên.
3. Nếu dữ liệu hợp lệ, tự động chuẩn hóa địa chỉ và gọi công cụ `add_new_room` để kích hoạt Nominatim API chuyển đổi thành tọa độ (lat, lng).
4. Lưu thông tin vào PostGIS (mặc định trạng thái hiển thị 7 ngày).
5. Trả về thông báo thành công dưới định dạng JSON card `A2UI_Card` để hiển thị xác nhận lên giao diện cho người dùng.
