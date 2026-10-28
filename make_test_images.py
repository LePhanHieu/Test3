from PIL import Image, ImageFilter, ImageEnhance
img = Image.open("goc.jpg").convert("RGB")
img.filter(ImageFilter.GaussianBlur(8)).save("test_mo.jpg")
ImageEnhance.Brightness(img).enhance(0.15).save("test_toi.jpg")
ImageEnhance.Brightness(img).enhance(3.5).save("test_sang.jpg")
img.resize((120, 120)).save("test_nho.jpg")