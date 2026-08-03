import requests
import re
import os

def normalize_channel_name(name):
    if not name:
        return ''
    # 先去除常见分隔符（空格、下划线、连字符）
    normalized = re.sub(r'[-\s_]+', '', name)
    # 只移除末尾的关键词（可附加'标清'等）
    normalized = re.sub(r'(频道|普清|标清|高清|超清|720P|1080P|HD)$', '', normalized, flags=re.IGNORECASE)
    # 再去掉可能残留的末尾分隔符
    normalized = re.sub(r'[-\s_]+$', '', normalized)
    return normalized.upper().strip()

def load_source_urls():
    source_path = "TV/sources.txt"
    urls = []
    if not os.path.exists(source_path):
        print(f"警告：未找到源地址文件 {source_path}，使用默认源")
        return ["https://live.fanmingming.com/tv/m3u/ipv6.m3u"]
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('http'):
                    urls.append(line)
                    print(f"加载源地址: {line}")
    except Exception as e:
        print(f"读取源地址文件失败: {e}")
        return ["https://live.fanmingming.com/tv/m3u/ipv6.m3u"]
    if not urls:
        print("警告：源地址文件为空，使用默认源")
        return ["https://live.fanmingming.com/tv/m3u/ipv6.m3u"]
    return urls

def load_categories_from_template():
    categories = {}
    current_category = None
    template_path = "TV/moban.txt"
    if not os.path.exists(template_path):
        print(f"错误：未找到模板文件 {template_path}")
        return categories
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ",#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    categories[current_category] = []
                elif current_category:
                    channel = line.strip()
                    if channel:
                        categories[current_category].append(channel)
    except Exception as e:
        print(f"读取模板文件出错: {e}")
    return categories

def load_channel_mapping():
    mapping = {}
    mapping_path = "TV/channel_mapping.txt"
    if not os.path.exists(mapping_path):
        return mapping
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                old_name, new_name = line.split(",", 1)
                std_key = normalize_channel_name(old_name.strip())
                std_value = normalize_channel_name(new_name.strip())
                mapping[std_key] = std_value
        print(f"加载映射表成功，共 {len(mapping)} 条映射")
    except Exception as e:
        print(f"加载映射表失败: {e}")
    return mapping

def parse_content(content):
    lines = content.split('\n')
    channels = {}
    current_group = '未分组'
    channel_count = 0
    is_m3u = '#EXTM3U' in content or '#EXTINF' in content

    if is_m3u:
        for i in range(len(lines)):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                group_match = re.search(r'group-title="([^"]*)"', line)
                group = group_match.group(1) if group_match else current_group
                group = normalize_channel_name(group)
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1].strip()
                name = normalize_channel_name(name)
                if i + 1 < len(lines):
                    url = lines[i + 1].strip()
                    if url and not url.startswith('#'):
                        if group not in channels:
                            channels[group] = []
                        channels[group].append((name, url))
                        channel_count += 1
                        current_group = group
    else:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if ",#genre#" in line:
                current_group = line.split(",")[0].strip()
                current_group = normalize_channel_name(current_group)
                if current_group not in channels:
                    channels[current_group] = []
            elif ',' in line and not line.startswith('#'):
                parts = line.split(',', 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    url = parts[1].strip()
                    if url and not url.startswith('#'):
                        name = normalize_channel_name(name)
                        if current_group not in channels:
                            channels[current_group] = []
                        channels[current_group].append((name, url))
                        channel_count += 1
    return channels, channel_count

def fetch_content(url):
    try:
        print(f"正在获取: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        content = response.text
        return parse_content(content)
    except Exception as e:
        print(f"请求失败: {e}")
        return {}, 0

def main():
    if not os.path.exists("TV"):
        os.makedirs("TV")
    source_urls = load_source_urls()
    print(f"\n共加载 {len(source_urls)} 个源地址")
    all_dicts = []
    success_count = 0
    for idx, url in enumerate(source_urls, 1):
        print(f"\n--- 处理第 {idx}/{len(source_urls)} 个源 ---")
        channels, count = fetch_content(url)
        if channels:
            all_dicts.append(channels)
            success_count += 1
            print(f"✅ 源 {idx} 获取成功，频道数: {count}")
        else:
            print(f"❌ 源 {idx} 获取失败或内容为空")
    print(f"\n📊 成功获取 {success_count}/{len(source_urls)} 个源")
    if not all_dicts:
        print("错误：未能获取任何有效内容")
        return

    # 合并所有分组字典（去重）
    merged = {}
    seen_urls = set()
    for d in all_dicts:
        for group, items in d.items():
            if group not in merged:
                merged[group] = []
            for name, url in items:
                if url not in seen_urls:
                    merged[group].append((name, url))
                    seen_urls.add(url)
    total_channels = sum(len(v) for v in merged.values())
    print(f"📊 合并后总计频道数: {total_channels}")

    categories = load_categories_from_template()
    if not categories:
        print("分类数据为空，请检查模板文件格式")
        return

    mapping = load_channel_mapping()

    sorted_content = []
    matched_count = 0

    for category, channel_list in categories.items():
        std_category = normalize_channel_name(category)
        category_items = []
        for group, items in merged.items():
            if group == std_category:
                category_items.extend(items)
        if category_items:
            sorted_content.append(f"{category},#genre#")
            for name, url in category_items:
                mapped_name = mapping.get(name, name)
                sorted_content.append(f"{mapped_name},{url}")
            sorted_content.append("")
            matched_count += len(category_items)

    # 未匹配的分组归入"其它"
    other_items = []
    for group, items in merged.items():
        found = False
        for cat in categories.keys():
            if normalize_channel_name(cat) == group:
                found = True
                break
        if not found:
            other_items.extend(items)

    if other_items:
        sorted_content.append("其它,#genre#")
        for name, url in other_items:
            mapped_name = mapping.get(name, name)
            sorted_content.append(f"{mapped_name},{url}")
        sorted_content.append("")

    output_path = "TV/live.txt"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted_content))
        print(f"\n✅ 多源合并完成，已保存为 {output_path}")
        print(f"📊 统计: {matched_count}个匹配频道, {len(other_items)}个未分类频道")
        print(f"📊 总计写入频道数: {matched_count + len(other_items)}")
    except Exception as e:
        print(f"保存文件时出错: {e}")

if __name__ == "__main__":
    main()