"""Family Schedule: an Infinite Campus Parent app for Tronbyt."""
load("render.star", "render")
load("http.star", "http")
load("cache.star", "cache")
load("encoding/json.star", "json")
load("time.star", "time")
load("schema.star", "schema")

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"

def get_schema():
    return schema.Schema(version = "1", fields = [
        schema.Text(id = "campus_url", name = "Campus base URL", desc = "HTTPS URL ending in /campus/, not the full login-page URL.", icon = "gear"),
        schema.Text(id = "app_name", name = "District app name", desc = "The district slug in your portal URL (before .jsp).", icon = "gear"),
        schema.Text(id = "timezone", name = "School timezone", desc = "IANA timezone, for example America/New_York.", default = "UTC", icon = "gear"),
        schema.Text(id = "username", name = "Campus username", desc = "Your Campus Parent username.", icon = "user"),
        schema.Text(id = "password", name = "Campus password", desc = "Stored in this private app configuration on your Tronbyt server.", icon = "key"),
    ])

def card(name, label, course, footer, color = "#80e5b4"):
    text = render.Text(course, font = "5x8", color = "#ffffff")
    scrolling = text.size()[0] > 64
    if scrolling:
        text = render.Marquee(width = 64, child = text, delay = 20, offset_end = 64)
    widget = render.Column(children = [
        render.Text(name[:12], font = "5x8", color = color),
        render.Text(label[:12], font = "5x8", color = "#ffd080"),
        text,
        render.Text(footer[:12], font = "5x8", color = "#82949f"),
    ])
    return widget if scrolling else render.Animation(children = [widget] * 45)

def screen(pages):
    return render.Root(child = render.Sequence(children = pages), delay = 100, max_age = 180, show_full_animation = True)

def error_screen(message):
    return screen([card("SCHEDULE", "CHECK CAMPUS", message, "Try later")])

def failed(key, message):
    cache.set(key, message, ttl_seconds = 900)
    return {"error": message}

def api(base, path, cookie, params = {}):
    response = http.get(base + path, params = params, headers = {"Cookie": cookie, "Accept": "application/json, text/plain, */*", "User-Agent": AGENT, "Referer": base + "apps/portal/parent/home"}, ttl_seconds = 0)
    if response.status_code != 200:
        return {"error": "API " + str(response.status_code)}
    body = response.body().strip()
    if not body.startswith("["):
        return {"error": "Campus reply"}
    return response.json()

def fetch_day(config, day):
    base = config.get("campus_url").rstrip("/") + "/"
    if not base.startswith("https://"):
        return {"error": "Use HTTPS"}
    account = base + ":" + config.get("app_name") + ":" + config.get("username")
    key = "family-schedule-v3:" + account + ":" + day
    saved = cache.get(key)
    if saved:
        return json.decode(saved)
    # A failed login is not retried every render. No credentials in logs or URLs.
    failure_key = "family-schedule-login:" + account
    previous_error = cache.get(failure_key)
    if previous_error:
        return {"error": previous_error}
    cache.set(failure_key, "Retry in 15m", ttl_seconds = 900)
    response = http.post(base + "verify.jsp", params = {"nonBrowser": "true"},
        headers = {"User-Agent": AGENT, "Accept": "text/html", "Referer": base + "portal/parents/" + config.get("app_name") + ".jsp"},
        form_body = {"username": config.get("username"), "password": config.get("password"), "appName": config.get("app_name"), "portalLoginPage": "parents"},
        form_encoding = "application/x-www-form-urlencoded", ttl_seconds = 0)
    if response.status_code != 200:
        return failed(failure_key, "Login " + str(response.status_code))
    cookies = {}
    for part in response.headers.get("Set-Cookie", "").split(","):
        pair = part.strip().split(";")[0]
        for name in ["JSESSIONID", "tomcat-cookie", "XSRF-TOKEN", "portalApp", "appName"]:
            if pair.startswith(name + "="):
                cookies[name] = pair[len(name) + 1:]
    if not cookies.get("JSESSIONID"):
        return failed(failure_key, "No session")
    cookie = "; ".join([name + "=" + value for name, value in cookies.items()])
    students = api(base, "api/portal/students", cookie)
    if type(students) == "dict":
        return failed(failure_key, students["error"])
    if not students:
        return failed(failure_key, "No students")
    result = []
    for student in students:
        # http.json represents JSON numbers as floats; IDs must not include '.0'.
        roster = api(base, "resources/portal/roster", cookie, {"personID": str(int(student["personID"])), "_date": day, "_expand": "{sectionPlacements-{term}}"})
        if type(roster) == "dict":
            return failed(failure_key, roster["error"])
        classes = {}
        for course in roster:
            for p in course.get("sectionPlacements", []):
                if p.get("instructionalDay") != True:
                    continue
                if p.get("startDate") and p["startDate"][:10] > day:
                    continue
                if p.get("endDate") and p["endDate"][:10] < day:
                    continue
                if not p.get("startTime") or not p.get("endTime"):
                    continue
                item = {"course": course.get("courseName", "Class"), "period": p.get("periodName") or "?", "start": p["startTime"], "end": p["endTime"]}
                item_key = p["startTime"] + ":" + str(course.get("sectionID")) + ":" + p["endTime"]
                classes[item_key] = item
        result.append({"name": student.get("firstName") or "Student", "classes": [classes[k] for k in sorted(classes.keys())]})
    # Cache only the reduced timetable, not passwords, tokens or the full student record.
    cache.set(key, json.encode(result), ttl_seconds = 14400)
    cache.set(failure_key, "", ttl_seconds = 1)
    return result

def abbreviation(course):
    name = course.upper()
    for word, short in [("HOMEROOM", "HOME"), ("ENGLISH", "ENG"), ("MUSTANG", "MUST"), ("CONNECTION", "CONN"), ("MATH", "MATH"), ("FRENCH", "FREN"), ("HISTORY", "HIST"), ("DESIGN", "DES"), ("SCIENCE", "SCI"), ("HEALTH", "H/PE"), ("BAND", "BAND")]:
        if word in name:
            return short
    return name[:4]

def day_page(name, weekday, classes, color):
    header = render.Box(width = 64, height = 8, child = render.Text(name[:6] + " - " + weekday, font = "5x8", color = color))
    rows = []
    for row in range(4):
        cells = []
        for col in range(2):
            index = row * 2 + col
            children = []
            if index < len(classes):
                item = classes[index]
                children = [
                    render.Text(item["period"][:2] + " ", font = "CG-pixel-3x5-mono", height = 6, color = color),
                    render.Text(abbreviation(item["course"]), font = "CG-pixel-3x5-mono", height = 6, color = "#ffffff"),
                ]
            cells.append(render.Box(width = 32, height = 6, color = "#0b1718" if row % 2 == 0 else "#040908", child = render.Row(children = children)))
        rows.append(render.Row(children = cells))
    if not classes:
        return render.Column(children = [header, render.Box(width = 64, height = 24, child = render.Text("No classes", font = "5x8", color = "#ffffff"))])
    return render.Column(children = [header] + rows)

def main(config):
    if not config.get("username") or not config.get("password") or not config.get("campus_url") or not config.get("app_name"):
        return screen([card("FAMILY", "SCHEDULE", "Set up Campus", "In settings")])
    now = time.now().in_location(config.get("timezone") or "UTC")
    day = now.format("2006-01-02")
    students = fetch_day(config, day)
    if type(students) == "dict":
        return error_screen(students["error"])
    pages = []
    for i, student in enumerate(students):
        color = "#80e5b4" if i % 2 == 0 else "#8bbfff"
        # Preserve the day's chronological order; overflow gets another screen.
        classes = student["classes"]
        for offset in range(0, max(1, len(classes)), 8):
            pages.append(day_page(student["name"], now.format("Mon"), classes[offset:offset + 8], color))
    return render.Root(child = render.Animation(children = pages), delay = 5000, max_age = 180, show_full_animation = True)
