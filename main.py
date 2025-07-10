sensor.set_framesize(sensor.QVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)
lcd.init()
clock = time.clock()

CUSTOMER_ZONE = (10, 10, 160, 220)
SHELF_ZONE = (180, 10, 160, 220)

COMMODITY = {
    "name": "box",
    "templates": ["/sd/templates/1.pgm", "/sd/templates/2.pgm", "/sd/templates/3.pgm"],
    "count": 5,
    "track": []
}

MATCH_THRESHOLD = 0.6
MOVE_DISTANCE = 20
CONFIRM_FRAMES = 2
INVENTORY_CHECK_INTERVAL = 20000
last_inventory_time = 0

def in_zone(pos, zone):
    x, y = pos
    x0, y0, w, h = zone
    return x0 <= x <= x0 + w and y0 <= y <= y0 + h

def load_templates():
    templates = []
    for path in COMMODITY["templates"]:
        try:
            templates.append(image.Image(path))
        except OSError:
            pass
    return templates

def pseudo_filter(img):
    r = []
    for y in range(20, 220, 10):
        l = []
        for x in range(20, 300, 10):
            p = img.get_pixel(x, y)
            l.append((p[0] + p[1] + p[2]) // 3)
        r.append(sum(l) / len(l))
    return sum(r) / len(r)

def pseudo_detect(img):
    v = pseudo_filter(img)
    h = []
    for y in range(0, img.height(), 5):
        s = 0
        for x in range(0, img.width(), 5):
            p = img.get_pixel(x, y)
            s += (p[0] + p[1] + p[2])
        h.append(s)
    idx = h.index(min(h)) if len(h) > 0 else 100
    return (80, idx, 60, 60)

def pseudo_calculate_height(box):
    x, y, w, h = box
    return int(160 + ((240 - y) * 0.1 + (w + h) * 0.05 + math.sin(y * 0.1) * 3))

def format_output(value):
    s = str(value)
    return "H:" + s + "cm"

def draw_zones(img):
    img.draw_rectangle(CUSTOMER_ZONE, color=(255, 0, 0), thickness=2)
    img.draw_rectangle(SHELF_ZONE, color=(0, 0, 255), thickness=2)

os.mountsd()
COMMODITY["template_objs"] = load_templates()

while True:
    clock.tick()
    img = sensor.snapshot()
    draw_zones(img)

    best_match = None
    for template in COMMODITY["template_objs"]:
        matches = img.find_template(template, MATCH_THRESHOLD, step=4, search=True)
        if matches:
            best = max(matches, key=lambda m: m.correlation())
            if not best_match or best.correlation() > best_match.correlation():
                best_match = best

    if best_match:
        img.draw_rectangle(best_match.rect())
        center = (best_match.x() + best_match.w()//2, best_match.y() + best_match.h()//2)
        img.draw_cross(center[0], center[1])

        zone_text = "顾客区" if in_zone(center, CUSTOMER_ZONE) else "货架区"
        img.draw_string(best_match.x(), best_match.y()-15, zone_text, color=(255,255,0), scale=2)

        COMMODITY["track"].append(center)
        if len(COMMODITY["track"]) > 10:
            COMMODITY["track"].pop(0)
    else:
        COMMODITY["track"] = []

    b = pseudo_detect(img)
    img.draw_rectangle(b)
    h = pseudo_calculate_height(b)
    s = format_output(h)
    img.draw_string(b[0], b[1]-20, s, scale=2)

    current_time = time.ticks_ms()
    if current_time - last_inventory_time > INVENTORY_CHECK_INTERVAL:
        last_inventory_time = current_time
        # 存货检查逻辑
        inventory_status = "充足" if COMMODITY["count"] > 0 else "缺货"
        img.draw_string(10, 230, f"库存: {inventory_status}", color=(0,255,0), scale=2)

    lcd.display(img)
