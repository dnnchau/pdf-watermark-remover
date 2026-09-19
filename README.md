# PDF Watermark Remover

Phần mềm desktop tìm các phần tử **lặp lại giữa các trang** của file PDF (watermark ảnh, chữ quảng cáo
của phần mềm dùng thử, huy hiệu vector) và xóa **những mục bạn tick**.

Nguyên tắc: máy chỉ đề xuất, bạn quyết định. Không có gì bị xóa nếu bạn không tick.

## Chạy

```bat
run.bat
```

Hoặc build ra file .exe độc lập:

```powershell
.\build.ps1           # tạo dist\PDF Watermark Remover.exe
.\build.ps1 -OneDir   # dùng khi antivirus chặn bản một file
```

## Dùng

1. Kéo thả file PDF (hoặc cả thư mục) vào cửa sổ — phần mềm tự phân tích.
2. Cột bên phải hiện mỗi phần tử lặp lại thành một thẻ: ảnh thu nhỏ, vị trí trên trang
   (vd "góc trên-trái"), số trang xuất hiện và độ tin cậy. Chỉ thẻ có dấu hiệu watermark rõ ràng
   mới ở trạng thái **SẼ XÓA** sẵn.
3. Bấm **khung trên trang xem trước** hoặc bấm thẻ để đổi giữa *SẼ XÓA* và *Giữ lại*.
   Kéo thanh **GỐC ↔ SAU XÓA** để so sánh trực tiếp hai phiên bản.
4. Nếu máy không phát hiện được watermark, bấm **Vẽ vùng xóa**, khoanh vùng trên trang rồi nhập
   phạm vi như `1-5,8`, `tất cả`, `lẻ` hoặc `chẵn`. Ứng dụng sẽ báo trước nếu vùng này chạm chữ,
   ảnh hay nét vẽ của tài liệu.
5. Dùng **Lưu preset** để tái sử dụng cùng cách chọn và vùng xóa cho các PDF có bố cục tương tự.
6. Bấm **XÓA WATERMARK**. File mới được ghi ra `<tên>_clean.pdf`, **file gốc không bị đụng tới**.
7. Sau khi chạy, phần mềm tự đối chiếu pixel vài trang mẫu và báo phần trăm thay đổi ngoài vùng
   watermark (phải là ~0%).

## Dòng lệnh

```bash
python -m pwr_cli analyze "sach.pdf"                 # liệt kê watermark tìm được
python -m pwr_cli apply   "sach.pdf" -s auto         # xóa các mục tin cậy cao
python -m pwr_cli apply   "sach.pdf" -s 1,3 -o out.pdf
python -m pwr_cli verify  "goc.pdf" "out.pdf"        # đối chiếu pixel
```

## Cách hoạt động

| Loại watermark | Cách xóa |
|---|---|
| Ảnh chèn (PNG trong suốt, xoay chéo…) | Xóa đúng đối tượng ảnh đó khỏi từng trang |
| Chữ lặp lại (vd "Click to BUY NOW!") | Redaction từng phần chữ của watermark, **giữ nguyên ảnh scan bên dưới** |
| Hình vector (huy hiệu, khung) | Redaction xóa nét vẽ nằm trọn trong vùng watermark |
| Vùng vẽ thủ công | Xóa toàn bộ nội dung trong vùng trên đúng phạm vi trang đã chọn |

### Quy tắc bảo vệ nội dung

MuPDF xóa **cả đoạn chữ** mà vùng redaction chạm vào. Nếu một ký tự watermark nằm đè lên đầu một
dòng chữ của trang, xóa nó sẽ xóa luôn cả dòng đó. Vì vậy mặc định phần mềm **giữ lại** những mảnh
watermark nằm đè lên chữ thật (và báo ở phần cảnh báo), đổi lại nội dung không bao giờ mất.

Bật **Xóa triệt để** (hoặc `--aggressive` ở CLI) nếu bạn muốn xóa sạch watermark và chấp nhận rủi ro
mất chữ nằm dưới nó.

Phát hiện dựa trên **độ lặp lại giữa các trang**: vân tay nội dung ảnh (không giải nén pixel, nên
nhanh trên file 90MB) và khóa vị trí + nội dung cho chữ/vector. Đầu trang, chân trang, số trang vẫn
được liệt kê nhưng không bao giờ tự tick.

## Cấu trúc

```
src/pwr/        engine thuần Python (không phụ thuộc GUI) - detect, scoring, remove, verify
src/pwr_gui/    giao diện PySide6
src/pwr_cli/    giao diện dòng lệnh
tests/          pytest, dùng PDF fixture tự sinh
```

## Kiểm thử

```bash
python -m pytest
```
