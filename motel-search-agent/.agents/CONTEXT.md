# Local Project Context & Secure Coding Standards

## Core Paved Roads
Mọi hành động của Agent phải tuân thủ các quy tắc sau để đảm bảo an toàn sản xuất:

1. **Tool Input Validation**: Mọi công cụ Agent (đặc biệt là các truy vấn PostgreSQL / PostGIS) phải xác thực tham số đầu vào qua Pydantic schemas nghiêm ngặt, tuyệt đối không được phân tích chuỗi thô (raw strings).
2. **Read-Only Enforcement**: Agent tìm kiếm chỉ được quyền gọi các lệnh SELECT. Cấm hoàn toàn mọi lệnh DROP, DELETE, UPDATE thông qua các hook bảo mật.
3. **Pre-Commit Remediation**: Nếu quá trình quét bảo mật (như Semgrep) phát hiện lỗ hổng (như khoá API hoặc thông tin nhạy cảm mã hóa cứng), Agent phải tự động thực hiện quy trình tái cấu trúc (refactor), sửa lỗi, chạy lại kiểm thử và chỉ cam kết khi mọi thứ đã sạch.