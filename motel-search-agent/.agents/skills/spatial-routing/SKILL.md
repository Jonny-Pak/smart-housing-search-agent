name: spatial-routing
description: Sử dụng khi người dùng tìm phòng theo khu vực, bán kính, hoặc địa điểm cụ thể.
# Workflow
1. Nếu chưa có tọa độ (lat, lng), dùng LLM trích xuất từ địa chỉ người dùng cung cấp.
2. Gọi công cụ `spatial_radius_search` từ MCP Server.
3. Chuyển đổi kết quả thô sang định dạng `A2UI_MapCard`.