import requests
import re
import os

def normalize_channel_name(name):
    """
    频道名标准化函数，与前端HTML保持一致
    规则：
    1. 去除所有空格、横线(-)、下划线(_)
    2. 去除清晰度/类型词：频道、普清、高清、HD（不区分大小写）
    3. 将所有英文字母转为大写
    """
    if not name:
        return ''

    # 1. 去除空格、横线、下划线
    normalized = re.sub(r'[-\s_]+', '', name)

    # 2. 去除清晰度/类型词（不区分大小写）
    remove_words = ['频道', '普清', '高清', 'HD']
    for word in remove_words:
        normalized = re.sub(word, '', normalized, flags=re.IGNORECASE)

    # 3. 英文字母转大写
    normalized = normalized.upper()

    # 4. 去除首尾空白
    return normalized.strip()

def load_source_urls():
    """从文件加载源地址列表"""
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
    """从模板文件加载分类和频道信息"""
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
    """加载频道名称映射表，并对key进行标准化"""
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
    """
    解析内容（自动识别M3U或TXT格式），返回 (channels_dict, channel_count)
    channels_dict: {group_name: [(normalized_name, url), ...]}
    注意：只做标准化，不应用映射表
    """
    lines = content.split('\n')
    channels = {}          # group -> list of (name, url)
    current_group = '未分组'
    channel_count = 0

    # 自动检测格式
    if '#EXTM3U' in content or '#EXTINF' in content:
        is_m3u = True
    else:
        is_m3u = False

    if is_m3u:
        # 解析M3U格式
        for i in range(len(lines)):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                group_match = re.search(r'group-title="([^"]*)"', line)
                group = group_match.group(1) if group_match else current_group
                # 标准化分组名
                group = normalize_channel_name(group)

                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1].strip()
                # 只标准化，不映射
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
        # 解析TXT格式
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if ",#genre#" in line:
                current_group = line.split(",")[0].strip()
                # 标准化分组名
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
    """从URL获取内容，自动识别格式并转换，返回 (channels_dict, channel_count)"""
    try:
        print(f"正在获取: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()

        content = response.text
        return parse_content(content)
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return {}, 0
    except Exception as e:
        print(f"处理内容时出错: {e}")
        return {}, 0

def merge_channels_dicts(dicts):
    """
    合并多个分组字典，去重（基于url去重，保留第一次出现的频道名）
    返回合并后的字典和总频道数
    """
    merged = {}
    seen_urls = set()
    total = 0
    for d in dicts:
        for group, items in d.items():
            if group not in merged:
                merged[group] = []
            for name, url in items:
                if url not in seen_urls:
                    merged[group].append((name, url))
                    seen_urls.add(url)
                    total += 1
    return merged, total

def main():
    # 确保TV目录存在
    if not os.path.exists("TV"):
        os.makedirs("TV")

    # 从文件加载源地址
    source_urls = load_source_urls()
    print(f"\n共加载 {len(source_urls)} 个源地址")

    # 获取并合并内容（直接获取分组字典）
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
    merged_channels, total_channels = merge_channels_dicts(all_dicts)
    print(f"📊 合并后总计频道数: {total_channels}")

    # 加载模板分类
    categories = load_categories_from_template()
    if not categories:
        print("分类数据为空，请检查模板文件格式")
        return

    # 加载映射表
    mapping = load_channel_mapping()

    # 输出结果：按模板分类整理
    sorted_content = []
    matched_count = 0

    # 遍历模板中的每个分类
    for category, channel_list in categories.items():
        # 查找merged_channels中与category匹配的分组
        # 注意：模板分类名可能包含中文，而分组名已被标准化，需要标准化后再比较
        std_category = normalize_channel_name(category)

        # 收集该分类下的所有频道（从merged_channels中提取）
        category_items = []
        # 遍历merged_channels的所有分组
        for group, items in merged_channels.items():
            # 如果分组名与模板分类名匹配（标准化后）
            if group == std_category:
                category_items.extend(items)

        # 如果该分类有频道，则输出
        if category_items:
            sorted_content.append(f"{category},#genre#")
            for name, url in category_items:
                # 应用映射表
                mapped_name = mapping.get(name, name)
                sorted_content.append(f"{mapped_name},{url}")
            sorted_content.append("")
            matched_count += len(category_items)

    # 统计未匹配的频道：属于merged_channels但不在任何模板分类中的频道
    # 由于我们按分组匹配，所有分组都会处理，但可能某些分组没有在模板中定义（如"未分组"或"4K频道"）
    # 这些分组会被忽略，归入"其它"
    # 更好的方式是收集所有已匹配的频道名，但这里我们简单处理：所有不在模板分类中的分组都归入"其它"
    other_items = []
    for group, items in merged_channels.items():
        # 检查这个分组是否在模板中（标准化后比较）
        found = False
        for category in categories.keys():
            if normalize_channel_name(category) == group:
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

    # 保存结果
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