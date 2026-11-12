# Diligo Auto Dashboard (bản 40)

Đọc báo cáo xuất từ Shopee / TikTok Seller Center → lưu kho lịch sử → xuất `index.html` + CSV cho Power BI.
Chỉ dùng thư viện chuẩn của Python (không cần cài pandas/openpyxl).

```
D:\Data_Input  ──► CAP_NHAT_BAO_CAO.bat ──► D:\Diligo_Dashboard_Output\index.html
                                           D:\Diligo_Dashboard_Output\HistoryStore_v2.json   (kho lịch sử)
                                           D:\Diligo_Dashboard_Output\Data_Output\*.csv       (Power BI)
```

## Khác gì so với V39

| | V39 | Bản 40 |
|---|---|---|
| Kho lịch sử | `HistoryStore.json` (21 MB) + `baseline_v25.json` đặt cạnh script, ghép lại mỗi lần chạy | Một file `HistoryStore_v2.json` (~12 MB) chứa cả lịch sử và baseline |
| Bản sao kho | 1 bản `HistoryStore_BACKUP.json` (21 MB) | 10 bản gần nhất, nén `.gz`, trong `HistoryStore_backups\` |
| `data_snapshot.json` | Bản sao 21 MB, không chương trình nào đọc | Bỏ |
| Code | 1 file 1.900 dòng (còn template HTML cũ không dùng) | Thư mục `diligo/` chia theo chức năng |
| Test | Kiểm tra tay | `tests/` chạy tự động, gồm so khớp từng byte với V39 |
| Thanh lọc | — | Nút **Đặt lại**: đưa ngày, sàn, nguồn, nhãn hàng, tuần, kiểu so sánh về mặc định khi mở báo cáo |

**Số liệu không đổi**: với cùng dữ liệu, `index.html`, toàn bộ CSV, file kiểm tra và kho lịch sử khớp từng byte với V39
(xem `tests/test_golden_v39.py`).

## Nâng cấp từ V39 (chỉ làm 1 lần)

1. Tải bản này về một thư mục mới, ví dụ `D:\Diligo_Dashboard_V40\`.
2. **Chép `baseline_v25.json` từ thư mục V39 sang thư mục V40** (file này không có trên GitHub vì chứa số liệu kinh doanh).
3. Giữ nguyên `D:\Diligo_Dashboard_Output\HistoryStore.json`. Không xóa, không sửa.
4. Chạy `CAP_NHAT_BAO_CAO.bat` trong thư mục V40.
   Lần đầu sẽ hiện các dòng `ℹ️ Gộp baseline…`, `ℹ️ Gộp lịch sử cũ…`, và tạo `HistoryStore_v2.json`.
5. Mở `index.html`, kiểm tra vài con số quen thuộc.

Nếu quên bước 2, chương trình **dừng lại và không ghi gì**, kèm hướng dẫn chép file.
Từ lần chạy thứ hai trở đi không cần `baseline_v25.json` nữa.

`HistoryStore.json` cũ không bị đụng tới. Nếu cần quay lại V39, chỉ cần chạy BAT của V39 như trước.
Lưu ý: dữ liệu nạp bằng bản 40 nằm trong `HistoryStore_v2.json`, V39 không thấy; nên chọn dùng một bản, không chạy xen kẽ.

## Dùng hằng tuần

1. Bỏ file mới vào đúng thư mục trong `D:\Data_Input` (giữ tên file gốc).
2. Chạy `CAP_NHAT_BAO_CAO.bat`, chờ `✅ XONG`.
3. Sau `✅ XONG` có thể xóa file raw trong `Data_Input`. **Không xóa `HistoryStore_v2.json`.**

Khôi phục kho từ bản sao: giải nén một file trong `HistoryStore_backups\` (7-Zip/WinRAR), đổi tên thành `HistoryStore_v2.json`.

## Đăng báo cáo lên link (GitHub Pages)

Sau khi cài một lần, mỗi lần chạy `CAP_NHAT_BAO_CAO.bat` sẽ tự đẩy `index.html` lên GitHub và in ra
`✅ LINK BÁO CÁO: https://quang0312.github.io/diligo-dashboard/`. Gửi link này cho mọi người; lần sau họ mở lại link cũ là thấy số mới
(GitHub cần 1–2 phút để cập nhật; bấm Ctrl+F5 nếu vẫn thấy bản cũ).

**Lưu ý:** repo public nên **ai có link cũng xem được**. Chỉ file `index.html` được đăng; Excel, CSV, kho lịch sử không bao giờ được gửi lên.

### Bước 1: Bật GitHub Pages (1 lần)
1. Mở repo trên GitHub, vào **Settings**, chọn **Pages** (menu bên trái).
2. Mục **Source** chọn **Deploy from a branch**. **Branch** chọn **main**, thư mục **/ (root)**, rồi bấm **Save**.

### Bước 2: Tạo token (1 lần)
1. Trên GitHub bấm ảnh đại diện (góc phải), chọn **Settings**, rồi **Developer settings** (cuối menu trái),
   **Personal access tokens**, **Fine-grained tokens**, **Generate new token**.
2. **Token name**: `diligo-dashboard`. **Expiration**: chọn thời hạn (ví dụ 1 năm; hết hạn thì tạo lại).
3. **Repository access**: chọn **Only select repositories**, rồi chọn `diligo-dashboard`.
4. **Permissions**: **Repository permissions**, mục **Contents**, chọn **Read and write**.
5. Bấm **Generate token**, rồi **copy** chuỗi bắt đầu bằng `github_pat_` (GitHub chỉ hiện 1 lần).

### Bước 3: Lưu token trên máy (1 lần)
1. Trong thư mục có `CAP_NHAT_BAO_CAO.bat`, tạo file **`GITHUB_TOKEN.txt`** (chuột phải, **New**, **Text Document**).
2. Mở bằng Notepad, dán token, lưu lại.
3. Kiểm tra tên file không bị thành `GITHUB_TOKEN.txt.txt` (bật **View**, **File name extensions** trong File Explorer để xem đuôi).

Token giống mật khẩu: không gửi qua chat, không đưa lên GitHub (`.gitignore` đã chặn file này).
Nếu BAT báo `⚠️ CHƯA ĐĂNG ĐƯỢC LÊN GITHUB`, báo cáo trên máy vẫn đã cập nhật; sửa theo lời nhắn (thường là token hết hạn) rồi chạy lại.

## Cấu trúc code

```
Diligo_Auto_Dashboard.py   điểm chạy (BAT gọi file này)
diligo/
  config.py                đường dẫn mặc định, tên file, bảng gán nhãn đặc biệt
  utils.py                 đọc số kiểu VN, ngày, kỳ trong tên file
  xlsx.py                  đọc .xlsx bằng thư viện chuẩn
  taxonomy.py              gán nhãn hàng / ngành hàng cho sản phẩm
  parsers/shopee.py        đọc file Shopee (Overview, nguồn, Live/Video/Affiliate, Ads, Finance)
  parsers/tiktok.py        đọc file TikTok
  collect.py               quét Data_Input, gọi đúng bộ đọc, khử trùng kỳ
  store.py                 kho lịch sử v2: đọc/ghi, chuyển đổi từ V39, ghép kỳ mới, bản sao
  dashboard.py             dựng dữ liệu dashboard (ghép baseline + lịch sử) và HTML
  export_csv.py            CSV cho Power BI
  publish.py               đăng index.html lên GitHub Pages
  cli.py                   luồng chạy chính
templates/dashboard.html   giao diện dashboard
AUTOMATION_CONFIG.json     vai trò / hạn xử lý / ngưỡng cảnh báo
GITHUB_PUBLISH.json        repo/nhánh để đăng báo cáo (token để riêng ở GITHUB_TOKEN.txt, không đưa lên)
tests/                     test tự động
```

## Chạy test

```
py -m unittest discover -s tests -v
```

So khớp với V39 trên dữ liệu thật (không đưa lên GitHub): tạo thư mục, ví dụ `D:\Diligo_Golden`, gồm
`Data_Input\`, `HistoryStore.json` (bản kiểu cũ), `baseline_v25.json`, rồi:

```
set DILIGO_GOLDEN_DIR=D:\Diligo_Golden
py -m unittest discover -s tests -v
```

Test này chạy V39 gốc (`tests/legacy_v39/`) và bản mới trên cùng dữ liệu qua 3 lần chạy (chuyển đổi kho, dựng lại không cần baseline,
nạp lại file trùng), rồi so từng byte mọi file đầu ra.

## Bảo mật

Repo đang **public**. `.gitignore` đã chặn file Excel/CSV/kho lịch sử/baseline. File `index.html` ở thư mục gốc chứa toàn bộ số liệu đã nhúng:
nếu không muốn công khai, hãy chuyển repo sang private hoặc dùng nơi lưu có mật khẩu.
