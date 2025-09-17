from pathlib import Path
import traceback
from PIL import Image, ImageDraw, ImageFont

from lib.telegram import send_telegram_message



def write_text_on_image(text: str,
                        img_path: str,
                        out_path: str,
                        font_path: str = "C:\\Users\\raymo\\AppData\\Local\\Microsoft\\Windows\\Fonts\\DejaVuSans-BoldOblique.ttf",
                        font_size: int = 64,
                        color: str = "#faf71e"):
    """
    Ghi `text` lên ảnh.
      • Cách mép trên ~20 % chiều cao.
      • Cách mép phải ~10 % chiều rộng.
      • Mặc định màu vàng tươi (#faf71e).
    """

    # 1. Load ảnh ở RGBA để dễ vẽ
    img = Image.open(img_path).convert("RGBA")
    W, H = img.size

    # 2. Font
    font = (ImageFont.truetype(font_path, font_size)
            if font_path else ImageFont.load_default())

    # 3. Vẽ chữ
    draw = ImageDraw.Draw(img)
    bbox   = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = W - tw - int(0.05 * W)        # phải 10 %
    y = int(0.1 * H)                 # trên 20 %

    # tuỳ chọn bóng nhẹ
    draw.text((x + 2, y + 2), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill=color)

    # 4. Chuyển sang RGB nếu lưu JPEG
    out_path = Path(out_path)
    if out_path.suffix.lower() in {".jpg", ".jpeg"}:
        img = img.convert("RGB")

    # 5. Lưu
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

def write_part_project(part_name: str,
                       project_name: str,
                       font_path: str  =  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                       font_size: int = 64):
    """
    Ghi tên phần dự án lên ảnh.
    """
    try:
        text = f"{part_name}"
        first_part = project_name.split("_")[0]
        img_path = f"/root/wan/projects/{project_name}/{first_part}.jpg"
        out_path = f"/root/wan/projects/{project_name}/{first_part}_part_{part_name}.jpg"
        write_text_on_image(text, img_path, out_path, font_path, font_size)
    except Exception as e:
        send_telegram_message(f"write_part_project error: {e}")
        traceback.print_exc()
        return False
if __name__ == "__main__":
    # Ví dụ sử dụng
    write_part_project(52, "BV1ez421e7Xj_1")
    
