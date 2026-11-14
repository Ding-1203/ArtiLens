import base64
import random
import re
import urllib

from fastapi import requests


def contains_year(text: str) -> bool:
    """
    是否包含年份
    """
    return re.search(r'\b(19|20)\d{2}\b', text) is not None


def is_reference_format(text: str) -> bool:
    """
    判断是否是参考文献条目（增强版）
    """
    text = text.strip()
    text_lower = text.lower()

    # 规则 1：编号开头（如 [1]、1.、(2)）
    if re.match(r'^\s*(\[\d+\]|\(\d+\)|\d+\.)', text):
        return True

    # 规则 2：包含参考文献关键词（缩紧后）
    keywords = [
        'et al.', 'arxiv:', 'doi:', 'vol.', 'no.', 'pp.',
        'in proceedings', 'in: ', 'transactions on',
        'ieee trans.', 'springer', 'cvpr', 'neurips', 'icml', 'iclr'
    ]
    if any(kw in text_lower for kw in keywords):
        return True

    # 规则 3：包含年份 + 至少两个作者
    if contains_year(text) and contains_multiple_person_names(text):
        return True

    return False


def is_figure_caption(text: str) -> bool:
    return re.match(r'\b(Fig|Figure)[^0-9]{0,2}(\d+)', text, re.IGNORECASE) is not None


import pandas as pd
from bs4 import BeautifulSoup
import re
from io import StringIO


def _similar_except_digits(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    diff_count = 0
    for ac, bc in zip(a, b):
        if ac != bc:
            if ac.isdigit() or bc.isdigit():
                return False
            diff_count += 1
    allowed_diff = max(2, len(a) // 4)
    return diff_count <= allowed_diff


def _extract_candidate_phrases(content: str, max_ngram: int = 4) -> list[str]:
    tokens = content.split()
    phrases = []
    for n in range(1, max_ngram + 1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n])
            phrases.append(phrase)
    return phrases


def _correct_html_table_by_content(html: str, content: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates = _extract_candidate_phrases(content, max_ngram=4)

    for cell in soup.find_all(["td", "th"]):
        original_text = (cell.get_text() or "").strip()
        if not original_text:
            continue
        for cand in candidates:
            if cand != original_text and _similar_except_digits(original_text, cand):
                cell.string = cand
                break
    return str(soup)


def _html_table_to_json(text_as_html: str) -> list:
    try:
        html_io = StringIO(text_as_html)
        tables = pd.read_html(html_io, header=[0, 1])
        df = tables[0]
        df.columns = [str(col).strip() for col in df.columns]
        return df.to_dict(orient="records")
    except ValueError as e:
        print("❌ HTML 表格解析失败:", e)
        return []


def extract_corrected_html_table_json(html: str, content: str) -> list[dict]:
    """
    根据文本内容修正 HTML 表格数据，并返回结构化 JSON（list of dict）。
    """
    corrected_html = _correct_html_table_by_content(html, content)
    return _html_table_to_json(corrected_html)


import fitz  # PyMuPDF
import os
from typing import Tuple, List
from PIL import Image
import numpy as np
import uuid


def extract_formula_image(
        pdf_path: str,
        page_number: int,
        points: List[Tuple[float, float]],
        output_path: str,
        dpi: int = 200
):
    """
    从 PDF 中提取指定坐标区域的图像（用于公式等）。
    坐标为 PixelSpace，相对于 layout_width x layout_height。
    """

    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]

    # 获取页面的像素大小（与 layout 相同）
    layout_width = 1700
    layout_height = 2200

    # 通过 dpi 计算渲染比例（默认 PDF 是 72 dpi）
    zoom_x = dpi / 72
    zoom_y = dpi / 72
    mat = fitz.Matrix(zoom_x, zoom_y)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    # 将原始点根据 layout → 渲染后的图像大小进行缩放
    def scale_point(p):
        x_ratio = (pix.width / layout_width)
        y_ratio = (pix.height / layout_height)
        return int(p[0] * x_ratio), int(p[1] * y_ratio)

    scaled_points = [scale_point(p) for p in points]

    # 取四个点的最小矩形框（可选更高级透视矫正）
    xs = [p[0] for p in scaled_points]
    ys = [p[1] for p in scaled_points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)

    # 裁剪像素图像
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    cropped = image.crop((x0, y0, x1, y1))

    # 保存图片
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cropped.save(output_path)
    # print(f"公式图已保存：{output_path}")


def extract_formula_number(text: str) -> str:
    match = re.search(r'\((\d+)\)\s*$', text)
    if match:
        return f"{int(match.group(1)):02d}"
    return "00"


def generate_unique_id(length=6) -> str:
    return uuid.uuid4().hex[:length]


def is_abstract(text: str) -> bool:
    """判断是否是摘要"""
    text_lower = text.lower()[:20]
    abstract_keywords = ['abstract', 'summary', '摘要', '概要']
    return any(keyword in text_lower for keyword in abstract_keywords) and len(text) > 500


def clean_text_both_sides(text):
    """
    从左右两侧同时清洗非字母字符，直到遇到字母字符
    :param text: 输入文本
    :return: 清洗后的文本
    """
    # 从左向右扫描，找到第一个字母字符
    start_index = 0
    for i in range(len(text)):
        if text[i].isalpha():
            start_index = i
            break
    else:  # 没有找到任何字母字符
        return ""

    # 从右向左扫描，找到最后一个字母字符
    end_index = len(text) - 1
    for i in range(len(text) - 1, -1, -1):
        if text[i].isalpha():
            end_index = i
            break

    return text[start_index:end_index + 1]


def is_person_name(text):
    """
    判断文本是否符合人名特征
    规则：
      1. 使用非字母字符进行分割
      2. 至少有两个非空部分
      3. 每个非空部分首字母大写，后续字母小写
    """
    # 使用非字母字符分割文本
    text = clean_text_both_sides(text)
    parts = re.split(r'[^a-zA-Z]+', text)
    # 过滤空字符串
    non_empty_parts = [part for part in parts if part]

    # 检查非空部分数量
    if len(non_empty_parts) < 2 or len(non_empty_parts) > 3:
        return False

    # 检查每个非空部分是否符合规则
    for part in non_empty_parts:
        if not part[0].isupper():
            return False
        if len(part) > 1 and not part[1:].islower():
            return False
    return True


def contains_multiple_person_names(text: str) -> bool:
    parts = [p.strip() for p in text.split(',')]
    name_count = sum(1 for part in parts if is_person_name(part))
    return name_count >= 2


def extract_person_names(text: str) -> list:
    """
    提取文本中的人名（一个或多个）
    :param text: 原始文本
    :return: 人名列表
    """
    text = clean_text_both_sides(text)

    # 判断是否是单独一个人名
    if is_person_name(text):
        return [text]

    # 如果是多个名字组合，尝试分割（优先用 and，再用 , ）
    # 允许连接词前后带空格
    raw_parts = re.split(r'\band\b|,|\*|\d', text)
    name_list = []

    for part in raw_parts:
        candidate = clean_text_both_sides(part.strip())
        if is_person_name(candidate):
            name_list.append(candidate)

    return name_list


def extract_https_urls(text):
    """
    提取 text 中的所有 https 开头的网址
    :param text: 输入文本
    :return: https 链接列表
    """
    return re.findall(r'https://[^\s]+', text)


import re

# 罗马数字映射
ROMAN_MAP = {
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
    'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
}

# 用于排除无编号的非正文段
EXCLUDE_SECTIONS = ["reference", "references", "acknowledgement", "appendix"]

# 关键词分类配置
SECTION_KEYWORDS = {
    "introduction": ["introduction", "background", "motivation"],
    "method": ["method", "methods", "approach", "framework"],
    "experiments": ["experiment", "experiments", "evaluation", "result", "results"],
    "conclusion": ["conclusion", "summary", "discussion"]
}


# 正规化标题
def normalize_title(title):
    return title.lower().replace(":", "").strip()


# 拆分为词汇
def tokenize(text):
    return re.findall(r'\b\w+\b', normalize_title(text))


# 提取标题编号前缀（用于分组），支持罗马数字、数字、字母
def extract_prefix_key(title):
    title = title.strip()
    match = re.match(r'^(\(?[A-Za-z0-9IVXLCDM]+\)?)[\.\s\]]+', title)
    if not match:
        return None
    raw = match.group(1).strip("()[]").upper()
    return raw  # 保留字符串形式，用作分组键


# 判断是否是一级标题（无小数点）
def is_top_level(title):
    return re.match(r'^\(?[A-Za-z0-9IVXLCDM]+\)?[\.\s\]]+', title) and not re.search(r'\d+\.\d+', title)


# 判断标题是否属于某类（通过关键词）
def classify_section(title):
    if any(ex in normalize_title(title) for ex in EXCLUDE_SECTIONS):
        return None
    tokens = tokenize(title)
    for key, keywords in SECTION_KEYWORDS.items():
        if any(k in tokens for k in keywords):
            return key
    return None


# 分组：按一级编号归类
def group_sections_by_prefix(sections):
    groups = {}
    current_prefix = None

    for sec in sections:
        prefix = extract_prefix_key(sec["title"])
        top_level = is_top_level(sec["title"])
        title_norm = normalize_title(sec["title"])

        # 如果是一级标题 -> 新开一个组
        if prefix and top_level:
            current_prefix = prefix
            groups[current_prefix] = {
                "title": sec["title"],
                "content": []
            }

        # 如果没有有效 current_prefix，直接跳过
        if not current_prefix:
            continue

        # 如果是 Reference/Acknowledgement/Appendix，则不追加内容
        if any(ex in title_norm for ex in EXCLUDE_SECTIONS):
            continue

        # 追加内容
        content_text = sec["content"] if isinstance(sec["content"], str) else "\n\n".join(sec["content"])
        groups[current_prefix]["content"].append(content_text)

    return groups


# 主函数：只提取匹配关键词的组，输出拼接字符串
def extract_core_sections(sections):
    grouped = group_sections_by_prefix(sections)
    result = {}

    for prefix, group in grouped.items():
        section_type = classify_section(group["title"])
        if section_type:
            full_text = f"{group['title']}\n\n" + "\n\n".join(group["content"])
            # 如果已经有这个类型，追加；否则初始化
            if section_type not in result:
                result[section_type] = []
            result[section_type].append(full_text)

    # 最后把每个类型的列表合并为一个字符串
    for key in result:
        result[key] = "\n\n".join(result[key])

    return result


import re
import feedparser
import urllib.parse
import time
import requests


# 定义提取引用的函数
def extract_references_section(parsed_data):
    sections = parsed_data.get("sections", [])
    for sec in sections:
        if sec.get("title", "") == "References":
            return sec.get("content", [])
    return []


def fix_hyphenated_words(text: str) -> str:
    # 查找 "abc- def" 形式，把中间的空格删掉
    return re.sub(r'(\w)-\s+(\w)', r'\1\2', text)


def extract_reference_title(citation: str) -> str:
    """
    按照句号拆分引用条目，选择最长部分作为标题
    """
    # 预处理：移除引用编号和项目符号
    citation = re.sub(r'^•\s*\[\d+\]\s*', '', citation).strip()

    # 按逗号和句号拆分
    segments = re.split(r'[.,]', citation)

    # 清理每个片段并保留原始长度
    cleaned_segments = []
    for segment in segments:
        clean_seg = segment.strip()
        # 跳过空片段和页码标记
        if not clean_seg or clean_seg.isdigit():
            continue
        # 跳过会议信息关键词
        if re.match(r'(In|Proc|Conf|Trans|Journal|Vol|pp?\.|Artificial Intelligence|IJCV|TPAMI|CVPR|ECCV|ICCV)',
                    clean_seg, re.I):
            continue
        cleaned_segments.append(clean_seg)

    # 选择最长的片段作为标题
    if not cleaned_segments:
        return citation  # 保底返回原始文本

    # 按长度降序排序
    sorted_segments = sorted(cleaned_segments, key=len, reverse=True)

    # 返回最长的片段（标题）
    return fix_hyphenated_words(sorted_segments[0].strip())


def get_arxiv_entry_from_title(title, timeout=0.5):
    """调用 arXiv API，根据标题获取第一篇匹配文章的信息，支持请求超时"""
    query = f"search_query=ti:{urllib.parse.quote(title)}&max_results=1"
    url = f"https://export.arxiv.org/api/query?{query}"

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.text)

        if not feed.entries:
            return None

        entry = feed.entries[0]
        return {
            "title": entry.title,
            "summary": entry.summary,
            "authors": [author.name for author in entry.authors],
            "published": entry.published,
            "link": entry.link
        }
    except requests.exceptions.Timeout:
        print(f"[ERROR] Request timed out for title: {title}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed for title: {title}, error: {e}")
        return None


import requests
import xml.etree.ElementTree as ET


def clean_title_for_search(title):
    # 将非字母数字字符替换为空格，并去掉多余空格
    cleaned = re.sub(r'[^a-zA-Z0-9]', ' ', title)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def search_arxiv(title, timeout=3, max_results=1):
    import urllib.parse
    import requests
    import xml.etree.ElementTree as ET

    base_url = "http://export.arxiv.org/api/query"
    cleaned_title = clean_title_for_search(title)
    print(f"[INFO] Searching arXiv for title: {cleaned_title}")
    encoded_title = urllib.parse.quote(cleaned_title)
    query = f'search_query=ti:"{encoded_title}"&max_results={max_results}'
    url = f"{base_url}?{query}"
    print(f"[INFO] Searching arXiv for url: {url}")

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        results = []
        entries = root.findall('atom:entry', ns)
        if not entries:
            print("[INFO] No matching entries found on arXiv.")
            return []   # 返回空列表，代表“没有查到”

        for entry in entries:
            title = entry.find('atom:title', ns).text.strip() if entry.find('atom:title', ns) is not None else ""
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ') if entry.find('atom:summary', ns) is not None else ""
            published = entry.find('atom:published', ns).text.strip() if entry.find('atom:published', ns) is not None else ""
            link = entry.find('atom:id', ns).text.strip() if entry.find('atom:id', ns) is not None else ""

            # 提取作者列表
            authors = []
            for author in entry.findall('atom:author', ns):
                name = author.find('atom:name', ns)
                if name is not None:
                    authors.append(name.text.strip())

            results.append({
                'title': title,
                'summary': summary,
                'authors': authors,
                'published': published,
                'link': link
            })

        return results

    except requests.exceptions.Timeout:
        print(f"[ERROR] Request timed out for title: {title}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed for title: {title}, error: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Unexpected error for title: {title}, error: {e}")
        return []


def build_rag_chunks(related_papers):
    chunks = []
    for entry in related_papers:
        if not entry:  # 跳过 None
            continue
        chunk = f"""[REFERENCE ARXIV ARTICLE]
Title: {entry.get('title', '')}
Authors: {', '.join(entry.get('authors', []))}
Published: {entry.get('published', '')}
Link: {entry.get('link', '')}
Summary: {entry.get('summary', '')}"""
        chunks.append(chunk)
    return chunks

import oss2
from typing import Dict, List, Optional

# --- 将图像上传到oss---
def _upload_to_oss(image_base64: str) -> Optional[str]:
    """
    Uploads a base64 encoded image to Alibaba Cloud OSS and returns the public URL.

    Args:
        image_base64: The raw base64 string from the frontend.

    Returns:
        The public URL of the uploaded image, or None on failure.
    """
    ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "YOUR_ACCESS_KEY_ID")
    ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "YOUR_ACCESS_KEY_SECRET")
    ENDPOINT = os.getenv("OSS_ENDPOINT", "https://oss-cn-hangzhou.aliyuncs.com")
    BUCKET_NAME = os.getenv("OSS_BUCKET_NAME", "your-bucket-name")
    # --------------------------------------------------------------------------

    try:
        auth = oss2.Auth(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, ENDPOINT, BUCKET_NAME)

        # 解码前端传入的base64注意
        image_data = base64.b64decode(image_base64)

        object_name = f"temp_images/{uuid.uuid4()}.png"

        print(f"[OSS] Uploading image to bucket '{BUCKET_NAME}' as '{object_name}'...")

        # 上传图片
        result = bucket.put_object(object_name, image_data)

        if result.status == 200:
            base_url = ENDPOINT.replace("https://", "")
            image_url = f"https://{BUCKET_NAME}.{base_url}/{object_name}"
            print(f"[OSS] Upload successful. Public URL: {image_url}")
            return image_url
        else:
            print(f"[OSS] Upload failed with status: {result.status}")
            return None

    except Exception as e:
        print(f"[OSS] An unexpected error occurred during upload: {e}")
        return None

# 测试示例
if __name__ == "__main__":
    # 示例用法
    result = search_arxiv("High-Resolution Image Synthesis with Latent Diffusion Models")
    print(result['title'])
    print(result['authors'])
    print(result['published'])
    print(result['link'])
    print(result['summary'])

    sections = [
        {
            "title": "PreInfo",
            "content": [
                "3",
                "2023",
                "2",
                "0",
                "2",
                "2",
                ":",
                "v",
                "i",
                "X",
                "r",
                "a"
            ]
        },
        {
            "title": "Arpit Bansal * 1 Hong-Min Chu * 1 Avi Schwarzschild 1 Soumyadip Sengupta 2 Micah Goldblum 3 Jonas Geiping 1 Tom Goldstein 1",
            "content": []
        },
        {
            "title": "Abstract",
            "content": [
                "Typical diffusion models are trained to accept a particular form of conditioning, most commonly text, and cannot be conditioned on other modalities without retraining. In this work, we propose a universal guidance algorithm that enables diffusion models to be controlled by arbitrary guidance modalities without the need to retrain any use-speciﬁc components. We show that our algorithm successfully generates quality images with guidance functions including segmentation, face recognition, object detection, and classiﬁer signals. Code is available at github.com/arpitbansal297/Universal-GuidedDiffusion."
            ]
        },
        {
            "title": "1. Introduction",
            "content": [
                "Diffusion models are powerful tools for creating digital art and graphics. Much of their success stems from our ability to carefully control their outputs, customizing results for each user’s individual needs. Most models today are controlled through conditioning. With conditioning, the diffusion model is built from the ground up to accept a particular modality of input from the user, be it descriptive text, segmentation maps, class labels, etc. While conditioning is a powerful tool, it results in models that are handcuffed to a single conditioning modality. If another modality is required, a new model needs to be trained, often from scratch. Unfortunately, the high cost of training makes this prohibitive for most users.",
                "A more ﬂexible approach to controlling model outputs is to use guidance. In this approach, the diffusion model acts as a generic image generator, and is not required to understand a user’s instructions. The user pairs this model with",
                "*Equal contribution 1Department of Computer Science, University of Maryland, College Park 2Department of Computer Science, University of North Carolina at Chapel Hill 3Department of Computer Science, New York University. Correspondence to: Arpit Bansal <bansal01@umd.edu>, Hong-Min Chu <hmchu@umd.edu>.",
                "a guidance function that measures whether some criterion has been met. For example, one could guide the model to minimize the CLIP score between the generated image and a text description of the user’s choice. During each iteration of image creation, the iterates are nudged down the gradient of the guidance function, causing the ﬁnal generated image to satisfy the user’s criterion.",
                "In this paper, we study guidance methods that enable any off-the-shelf model or loss function to be used as guidance for diffusion. Because guidance functions can be used without re-training or modiﬁcation, this form of guidance is universal in that it enables a diffusion model to be adapted for nearly any purpose.",
                "From a user perspective, guidance is superior to conditioning, as a single diffusion network is treated like a foundational model that provides universal coverage across many use cases, both commonplace and bespoke. Unfortunately, it is widely believed that this approach is infeasible. While early diffusion models relied on classiﬁer guidance (Dhariwal & Nichol, 2021), the community quickly turned to classiﬁer-free schemes (Ho & Salimans, 2022) that require a model to be trained from scratch on class labels with a particular frozen ontology that cannot be changed (Nichol et al., 2021; Rombach et al., 2022; Bansal et al., 2022).",
                "The difﬁculty of using guidance stems from the domain shift between the noisy images used by the diffusion sampling process and the clean images on which the guidance models are trained. When this gap is closed, guidance can be performed successfully. For example, Nichol et al. (2021) successfully use a CLIP model as guidance, but only after re-training CLIP from scratch using noisy inputs. Noisy retraining closes the domain gap, but at a very high ﬁnancial and engineering cost. To avoid the additional cost, we study methods for closing this gap by changing the sampling scheme, rather than the model.",
                "To this end, our contributions are summarized as follows:",
                "• We propose an algorithm that enables universal guidance for diffusion models. Our proposed sampler evaluates the guidance models only on denoised images, rather than noisy latent states. By doing so, we close the domain gap that has plagued standard guidance methods. This strategy provides the end-user with the ﬂexibility to work with a wide range of guidance modalities and even multiple modalities simultaneously. The underlying diffusion model remains ﬁxed and no ﬁne-tuning of any kind is necessary.",
                "• We demonstrate the effectiveness of our approach for a variety of different constraints such as classiﬁer labels, human identities, segmentation maps, annotations from object detectors, and constraints arising from inverse linear problems."
            ]
        },
        {
            "title": "2. Background",
            "content": [
                "We ﬁrst brieﬂy review the recent literature on the core framework behind diffusion models. Then, we deﬁne the problem setting of controlled image generation and discuss previous related works."
            ]
        },
        {
            "title": "2.1. Diffusion Models",
            "content": [
                "Diffusion models are strong generative models that proved powerful even when ﬁrst introduced for image generation (Song & Ermon, 2019; Ho et al., 2020). The approach has been successfully extended to a number of domains, such as audio and text generation (Kong et al., 2020; Huang et al., 2022; Austin et al., 2021; Li et al., 2022).",
                "We introduce (unconditional) diffusion formally, as it is helpful in describing the nuances of different types of models. A diffusion model is deﬁned as a combination of a T-step forward process and a T-step reverse process. Conceptually, the forward process gradually adds Gaussian noise of different magnitudes to a clean data point z0, while the reverse process attempts to gradually denoise a noisy input in hopes of recovering a clean data point. More concretely, given an array of scalars representing noise scales {αt}T t=1 and an initial, clean data point z0, applying t steps of the forward process to z0 yields a noisy data point",
                "A diffusion model is a learned denoising network €g. It is trained so that for any pair (zo, t) and any sample of ¢,",
                "The reverse process takes the form q(zt−1|zt,z0) with various detail deﬁnitions, where q(·|·) is generally parameterized as a Gaussian distribution. Different works also studied different approximations of the unknown q(zt−1|zt,z0) used to perform sampling. For example, denoising diffusion implicit model (DDIM) (Song et al., 2021a) ﬁrst computed a predicted clean data point",
                "and sample z,—1 from q(z¢—1|2, 20) by replacing unknown zg With 29. On the other hand, while the details of individual sampling methods vary, all sampling methods produce 2,1 based on current sample z;, current time step ¢ and a predicted noise €. To ease the notation burden, we define a function S(-,-,-) as an abstraction of the sampling method, where z,-1 = S(z1,é,t)."
            ]
        },
        {
            "title": "2.2. Controlled Image Generation",
            "content": [
                "In this paper, we focus on controlled image generation with various constraints. Consider a differentiable guidance function f, for example a CLIP feature extractor or a segmentation network. When applied to an image, we obtain a vector c = f(x). We also consider a function ¢(-,-) that measures the closeness of two vectors c and c’. Given a particular choice of c, which we call a prompt, the corresponding constraint (based on c, ¢, and f) is formalized as L(c, f(z)) © 0, and we aim to generate a sample z from the image distribution satisfying the constraint. In plain words, we want to generate an in-distribution image that matches the prompt.",
                "Prior work that studied controlled generative diffusion mainly falls into two categories. We refer to the ﬁrst category as conditional image generation, and the second category as guided image generation. Next, we discuss the characteristics of each category and better situate our work among existing methods.",
                "Conditional Image Generation. Methods from this category require training new diffusion models that accept the prompt as an additional input (Ho & Salimans, 2022; Bansal et al., 2022; Nichol et al., 2021; Whang et al., 2022; Wang et al., 2022a). For example, Ho & Salimans (2022) proposed classiﬁer-free guidance using class labels as prompts, and trained a diffusion model by linear interpolation between unconditional and conditional outputs of the denoising networks. Bansal et al. (2022) studied the case where the guidance function is a known linear degradation operator, and trained a conditional model to solve linear inverse problems. Nichol et al. (2021) further extended classiﬁer-free guidance to text-conditional image generation with descriptive phrases as prompts, and trained a diffusion model to enforce the similarity between the CLIP (Radford et al., 2021) representations of the generated images and the text prompts. These methods are successful across different types of constraints, however the requirement to retrain the diffusion model makes them computationally intensive.",
                "Guided Image Generation. Works in this category employed a frozen pre-trained diffusion model as a foundation model, but modify the sampling method to guide the image generation with feedback from the guidance function. Our method falls into this category. Prior work that studied guided image generation did so with a variety of restrictions and external guidance functions (Dhariwal & Nichol, 2021; Kawar et al., 2022; Wang et al., 2022b; Chung et al., 2022a; Lugmayr et al., 2022; Chung et al., 2022b; Graikos et al., 2022). For example, Dhariwal & Nichol (2021) proposed classiﬁer guidance, where they trained a classiﬁer on images of different noise scales as the guidance function f, and included gradients of the classiﬁer during the sampling",
                "process. However, a classiﬁer for noisy images is domainspeciﬁc and generally not readily available – an issue our method circumvents. Wang et al. (2022b) assumed the external guidance functions to be linear operators, and generated the component of images residing in the null space of linear operators with the foundation model. Unfortunately, extending that method to handle non-linear guidance functions is non-trivial. Chung et al. (2022a) studied general guidance functions, and modiﬁed the sampling process with the gradient of guidance function calculated on the expected denoised images. Nevertheless, the authors only presented results with simpler non-linear guidance functions such as non-linear blurring.",
                "In this work, we study universal guidance algorithms for guided image generation with diffusion models using any off-the-shelf guidance functions f, such as object detection or segmentation networks."
            ]
        },
        {
            "title": "3. Universal Guidance",
            "content": [
                "We propose a guidance algorithm that augments the image sampling method of a diffusion model to include guidance from an off-the-shelf auxiliary network. Our algorithm is motivated by an empirical observation that the reconstructed clean image ˆz0 obtained by Equation (3), while naturally imperfect, is still appropriate for a generic guidance function to provide informative feedback to guide the image generation. In Section 3.1, we motivate our forward universal guidance by extending classiﬁer guidance (Dhariwal & Nichol, 2021) to leverage this observation and handle generic guidance functions. In Section 3.2, we propose a supplementary backward universal guidance to help enforce the generated image to satisfy the constraint based on the guidance function f. In Section 3.3, we discuss a simple yet helpful self-recurrence trick to empirically improve the ﬁdelity of generated images."
            ]
        },
        {
            "title": "3.1. Forward Universal Guidance",
            "content": [
                "To guide the generation with information from the external guidance function f and the loss function /, an immediate thought is to extend classifier guidance (Dhariwal & Nichol, 2021) to accept any general guidance function. Concretely, given a class prompt c, classifier guidance performs classification-guided sampling by replacing €9(z;,, ¢) in each sampling step S(z;,,t) with",
                "Defining ¢..(-,-) to be the cross-entropy loss and f,; to be the guidance function that outputs classification probability, Equation (4) can be re-writtern as",
                "Algorithm 1 Universal Guidance",
                "Parameter: Recurrent steps k, gradient steps m for backward guidance and guidance strength s(t),",
                "noise scales {a;}7_,, guidance function f, loss function £, and prompt c fort=T,T-1,..., for n= 1,2 ; Calculate 29 as Equation (3) Calculate €, using forward universal guidance as Equation (6) ifm > 0 then Calculate Azo by minimizing Equation (7) with m steps of gradient descent Perform backward universal guidance by €o + €9 — V/ar/(1 — ax) Azo ( Equation (9)) end if 24-1 <— S(Zt, €9,t) e ~N(0,1) ae Var/aia1t+ Jl = o/s end for end for",
                "However, directly replacing f.; and ¢.¢ with any off-theshelf guidance and loss functions does not work in practice, as f is most likely trained on clean images and fails to provide meaningful guidance when the input is noisy.",
                "To address the issue, we leverage the fact that €9(z;, t) predicts the noise added to the data point, and we can therefore obtain a predicted clean image Zp by Equation (3). We propose to instead calculate the guidance based on the predicted clean data point as",
                "where s(t) controls the guidance strength for each sampling step and",
                "as in Equation (3). We term Equation (6) forward universal guidance, or forward guidance in short. In practice, applying forward guidance effectively brings the generated image closer to the prompt while keeping the generation trajectory in the data manifold. We note that a related approach is also studied in (Chung et al., 2022a), where the guidance step is computed based on E[z0|zt]. The approach drew inspiration from the score-based generative framework (Song et al., 2021b), but resulted in a different update method."
            ]
        },
        {
            "title": "3.2. Backward Universal Guidance",
            "content": [
                "As will be shown in Section 4.2, we observe that forward guidance sometimes over-prioritizes maintaining the “real-",
                "ness” of the image, resulting in an unsatisfactory match with the given prompt. Simply increasing the guidance strength s(t) is suboptimal, as this often results in instability as the image moves off the manifold faster than the denoiser can correct it.",
                "To address the issue, we propose backward universal guidance, or backward guidance in short, to supplement forward guidance and help enforce the generated image to satisfy the constraint. The key idea of backward guidance is to optimize for a clean image that best matches the prompt based on Zo, and linearly translate the guided change back to the noisy image space at step t. Concretely, instead of directly calculating V-,¢(c, f(Z0)), we compute a guided change Azp in clean data space as",
                "Empirically, we solve Equation (7) with m-step gradient descent, where we use A = 0 as a starting point. Since 29 + Azo minimizes ¢(c, f(z)) directly, Azo is the change in clean data space that best enforces the constraint. Then, we translate Azo back to the noisy data space of z,; by calculating the guided denoising prediction € that satisfies",
                "Reusing Equation (3), we can rewrite € as an augmentation to the original denoising prediction €9(z;,t) by",
                "Comparing to forward guidance, backward guidance (as Equation (9)) produces an optimized direction for the generated image to match the given prompt, and hence prioritizes enforcing the constraint. Furthermore, calculation of a gradient step for Equation (7) is computationally cheaper than forward guidance (Equation (6)), and we can therefore afford to solve Equation (7) with multiple gradient steps, further improving the match with the given prompt.",
                "We note that the names “forward” and “backward” are used analogously to the forward and backward Euler methods."
            ]
        },
        {
            "title": "3.3. Per-step Self-recurrence",
            "content": [
                "Unfortunately, when we apply our universal guidance to standard generation pipelines, we often ﬁnd images with artifacts and strange behaviors that clearly separate them from natural images. Similar observations have been made in (Lugmayr et al., 2022; Wang et al., 2022b), where linear guidance functions are studied. Our attempts to prioritize realness by decreasing s(t) proved ineffective; the sweet spot that both ensures the realness and guidance constraint satisfaction doesn’t always exist, especially for complex"
            ]
        },
        {
            "title": "Universal Guidance for Diffusion Models",
            "content": [
                "Figure 2: An example of how self-recurrence helps segmentation-guided generation. The left-most ﬁgure is the given segmentation map, and the images generated with recurrence steps of 1, 4 and 10 follow in order.",
                "guidance functions. We conjecture that the guidance direction produced by our universal method is not always related to the realness of the images when the guidance function creates too much information loss, causing the image to stray from the natural image sampling trajectory.",
                "Inspired by (Lugmayr et al., 2022; Wang et al., 2022b), we address the issue by applying per-step self-recurrence. More concretely, after z,_1 = (zz, €;,¢) is sampled, we re-inject random Gaussian noise €’ ~ NV (0,1) to 2,1 to obtain z; by",
                "Equation (10) ensures z; to have proper noise scale for input at time step t. We repeat the self-recurrence k times before continuing the sampling for step t — 1. Intuitively, the self-recurrence allows exploration of different regions of the data manifold at the same noise scale, allowing more budget to find a solution that satisfies both guidance and image quality. Empirically, we find that our self-recurrence can keep the realness of the generated image with a proper guidance strength s(t) that ensures the match with the given prompt. We illustrate an example of how self-recurrence improves the harmony of generated images in Figure 2.",
                "We summarize our universal guidance algorithm composed of forward universal guidance, backward universal guidance and per-step self-recurrence in Algorithm 1. For simplicity, the algorithm assumes only one guidance function, but can be easily adapted to handle multiple pair of (f,l). Additionally, the objectives of the forward and backward guidance do not have to be identical, allowing different ways to simultaneously utilize multiple guidance functions."
            ]
        },
        {
            "title": "4. Experiments",
            "content": [
                "In this section, we present results testing our proposed universal guidance algorithm against a wide variety of guidance functions. Speciﬁcally, we experiment with Stable Diffusion (Rombach et al., 2022), a diffusion model that is able to perform text-conditional generation by accepting text prompt as additional input, and experiment with a purely unconditional diffusion model trained on ImageNet (Deng et al., 2009), where we use pre-trained model provided by",
                "Figure 3: We compare the ability to match given text prompts between our universal guidance algorithm and text-conditional model trained from scratch. The results demonstrate that our universal algorithm is comparable to specialized conditional model on the ability to generate quality images that satisfy the text constraints.",
                "OpenAI (Dhariwal & Nichol, 2021). We note that Stable Diffusion, while being a text-conditional generative model, can also perform unconditional image generation by simply using an empty string for the text prompt. We ﬁrst present the experiment on Stable Diffusion for different guidance functions in Section 4.1, and present the results on ImageNet diffusion model in Section 4.2."
            ]
        },
        {
            "title": "4.1. Results for Stable Diffusion",
            "content": [
                "In this section, we present the results of guided image generation using Stable Diffusion as the foundation model. The guidance functions we experiment with include the CLIP feature extractcor (Radford et al., 2021), a segmentation network, a face recognition network and an object detection network. For experiments on Stable Diffusion, we discover that applying forward guidance already produce high-quality images that match the given prompt, and hence set m = 0. To perform forward guidance on Stable Diffusion, we forward the predicted clean latent variable computed by Equation (3) through the image decoder of Stable Diffusion to obtain predicted clean images. We discuss the results and implementation details for each guidance function in its corresponding subsection.",
                "CLIP Guidance. CLIP (Radford et al., 2021) is a state-ofthe-art text-to-image similarity model developed by OpenAI. To apply our algorithm to text-guided image generation, we use the image feature extractor of CLIP as the guidance function. We construct a loss function that calculates the negative cosine similarity between an image embedding and the CLIP text embedding produced by a given text √ prompt. We use s(t) = 10 1 − αt and k = 8 and use Stable Diffusion as an unconditional image generator.",
                "We generate images guided by a number of text prompts. To further assess our universal guidance algorithm and compare guidance and conditioning, we also generate images using classical, text-conditional generation by Stable Diffusion with identical prompts as inputs, and summarize the results in Figure 3. The results in Figure 3 show that our algorithm can guide the generation to produce high-quality images that match the given text description, and are comparable with images generated by the specialized text-conditioning model.",
                "Segmentation Map Guidance. To perform guided image generation using a segmentation map as prompt, we use a MobileNetV3-Large (Howard et al., 2019) with a segmen-",
                "tation head, and a publicly available pre-trained model in PyTorch (Paszke et al., 2019). As the segmentation network outputs per-pixel classification probability, we construct a loss function @ as the sum of per-pixel cross-entropy loss between a given prompt and the predicted segmentation of generated images. We set s(t) = 400-1 — a and k = 10.",
                "In our experiment, we combine segmentation maps that depict objects of different shapes with new text prompts. We use the text prompt as a ﬁxed additional input to Stable Diffusion to perform text-conditional sampling, and guide the text-conditional generated images to match the given segmentation maps. Results are presented in Figure 4. From Figure 4, we see that the generated images show a clear separation between object and background that matches the given segmentation map nearly perfectly. The generated object and background also each match their descriptive text (i.e. dog breed and environment description). Furthermore, the generated images are overall highly realistic.",
                "Face Recognition Guidance. To guide image generation to resemble the face of a given person, we compose a guidance function that combines a face detection module and a face recognition module. This setup pro-",
                "duces a facial attribute embedding from an input face image. We use multi-task cascaded convolutional networks (MTCNN) (Zhang et al., 2016) as the face detection module, and use facenet (Schroff et al., 2015) as the face recognition module. The guidance function f hence crops out the detected face and outputs a facial attribute embedding as prompt, while we use /;-loss between embedding as the loss function @. We note that to compute the guidance direction in our algorithm, we only backpropagate through the facenet and treat the face cropping mask produced by MTCNN as an oracle input, as MTCNN utilizes nonmaximum suppression (Neubeck & Van Gool, 2006) which is non-differentiable. Here we set s(t) = 20000 /I — a; and and k = 2.",
                "We explore different combinations of face guidance and text prompts. Similarly to the segmentation case, we use the text prompt as a ﬁxed additional conditioning to Stable Diffusion and guide this text-conditional trajectory with our algorithm so that the face in the generated image looks similar to the face prompt. In Figure 5, we clearly see that the facial characteristics of a given face prompt are reproduced almost perfectly on the generated images. The descriptive text of either background, material, or style is also realized correctly and blends nicely with the generated faces.",
                "Object Location Guidance For Stable Diffusion, we also present the results guiding image generation with an object detection network. For this experiment, we use FasterRCNN (Ren et al., 2015) with Resnet-50-FPN backbone (Li et al., 2021), a publicly available pre-trained model in Pytorch, as our object detector. We use bounding boxes with class labels as our object location prompt. We construct a loss function ¢ by the sum of three individual losses, namely (1) anchor classification loss, (2) bounding box regression loss and (3) region label classification loss, where (1) and (2) are computed on the region proposal head while (3) is computed on the region classification head. We note that, compared to standard R-CNN training, we drop the additional bounding box alignment loss on region classification head. We found that our loss construction helps to produce objects of correct categories for each location prompt. We set s(t) = 100/1 — a and k = 3.",
                "We again experiment with different combinations of text prompt and object location prompt, and similarly use the text prompt as a ﬁxed conditioning to Stable Diffusion. Using our proposed guidance algorithm, we perform guided image generation that generates and matches the objects presented in the text prompt to the given object locations."
            ]
        },
        {
            "title": "Universal Guidance for Diffusion Models",
            "content": [
                "Figure 8: We show that unconditional diffusion models trained on ImageNet can be guided with CLIP to generate high-quality images that match the text prompts, even if these generated images should be out of distribution.",
                "The results are presented in Figure 6. We observe from Figure 6 that objects in the descriptive text all appear in the designated location with the appropriate size indicated by the given bounding boxes. Each location is ﬁlled with appropriate, high-quality generations that align with varied image content prompts, ranging from “beach” to “oil painting”.",
                "Style Guidance Finally, we conclude our experiments on Stable Diffusion by guiding the image generation based on a reference style given by a style image. To achieve so, we capture the reference style from the style image by the image feature extractor from CLIP, and use the resulting image embedding as prompts. The loss function calculates the negative cosine similarity between the embedding of generated images and the embedding of the style image. Similar to previous experiments, we control the content using text input as additional conditioning to the Stable Diffusion model.",
                "We experiment with combinations of different style images and different text prompts, and present the results in Figure 7. From Figure 7, we can see that the generated images contain contents that match the given text prompts, while exhibiting style that matches the given style images. In this experiment √ we set s(t) = 6 · 1 − αt and k = 6. Furthermore, in order to control the amount of content we set the scale γ, a parameter of Stable Diffusion that balances the textconditional generation and unconditional generation, as 3.0, 3.0, and 4.0 respectively for each column."
            ]
        },
        {
            "title": "4.2. Results for ImageNet Diffusion",
            "content": [
                "In this section, we present results for guided image generation using an unconditional diffusion model trained on ImageNet. We experiment with CLIP guidance, object location guidance and a hybrid guided image generation task which we term segmentation-guided inpainting. We will discuss results and implementations of each guidance in its corresponding subsection.",
                "Figure 9: Generation guided by object detection with the unconditional ImageNet model. Images generated with both forward and backward guidance are realistic and have the desired objects in the designated locations. In contrast, images generated using only forward guidance exhibit objects of the incorrect category or with inaccurate position/size.",
                "CLIP Guidance. We use the same construction of f and ¢ for Stable Diffusion to perform CLIP-guided generation. We use only forward guidance for this experiment. To assess the limit of our universal guidance algorithm, we hand-crafted text prompts such that the matching images are expected to be out of distribution. In particular, our text prompts either designate art styles that are far from realistic or designate objects that do not belong to any possible class label of ImageNet. We present the results in Figure 8, and from the results, we clearly see that our algorithm still successfully guides the generation to produce quality images that also match the text prompts. For all three images, we have s(t) = w1 — ay, where w is 2, 5 and 2 respectively and kis 10, 5 and 10 respectively.",
                "Object Location Guidance. Similar to object location guidance for Stable Diffusion, we also use the same network architecture and the same pre-trained model as our object detection network, and construct an identical loss function ¢ for our guidance algorithm. However, unlike Stable Diffusion, object locations are the only prompts available for guided image generation. For this experiment, we use s(t) = 1001 — a and k = 3.",
                "We again experiment with different object location prompts using two conﬁgurations of our algorithm, namely (1) using only forward universal guidance and (2) using both forward and backward universal guidance. We observe from Figure 8 that applying both forward and backward guidance generates images that are realistic and the objects matches the prompt nicely. On the other hand, while images generated using only forward guidance remain realistic, they feature objects with mismatching categories and locations.",
                "Figure 10: Our guidance algorithm can incorporate feedback from multiple guidance functions. The ﬁrst column shows the prompt for inpainting. The second column shows classiﬁer-guided inpainting, where dog images with close matches to inpainting prompt are generated. The third column shows images generated with both classiﬁer and segmentation guidance, where realistic dogs are generated exactly on the masked regions. The results show that our algorithm handles multiple guidance functions effectively.",
                "The results demonstrate the effectiveness of our universal guidance algorithm, and also validate the necessity of our backward guidance.",
                "Segmentation-Guided Inpainting. In this experiment, we aim to explore the ability of our algorithm to handle multiple guidance functions. We perform guided image generation with combined guidance from an inpainting mask, a classifier and a segmentation network. We first generate images with masked regions as the prompt for inpainting. We then pick an object class c as the prompt for classification and generate a segmentation mask where the masked regions are considered foreground objects of the same class c. We use @2 loss on the non-masked region as the loss function for inpainting, and set the corresponding s(t) = 0, or equivalently only use backward guidance for inpainting. We use the same segmentation network as described in Section 4.1 with s(t) = 200./1 — a. For classification guidance, we use the classifier that accepts noisy input (Dhariwal & Nichol, 2021), and perform the original classifier guidance Equation (4) instead of our forward guidance. The results summarized in Figure 10 show that when using both inpainting and classifier as guidance, our algorithm generates realistic images that both match the inpainting prompt and can be classified correctly to the given object class. Adding in segmentation guidance, our algorithm further improves the generated images with a near-perfect match to both the segmentation map and inpainting prompt while maintaining realism. This demonstrates that our algorithm can effectively combine the feedback from individual guid-",
                "ance functions."
            ]
        },
        {
            "title": "5. Limitations",
            "content": [
                "Generation using universal guidance is typically slower than standard conditional generation for several reasons. Empirically, multiple iterations of denoising are required at every noise level t to generate high-quality images with complex guidance functions. However, the time complexity of our algorithm scales linearly with the number of recurrence steps k, which slows down image generation when k is large. Also, as demonstrated in the main paper, backward guidance is required in certain scenarios to help generate images that match the given constraint. Computing backward guidance requires performing minimization with a multistep gradient descent inner loop. While proper choices of gradient-based optimization algorithms and learning rate schedules signiﬁcantly speed up the convergence of minimization, the time it takes to compute backward guidance inevitably becomes longer when the guidance function is itself a very-large neural network. Finally, we note that, to get optimal results, sampling hyper-parameters must be chosen individually for each guidance network."
            ]
        },
        {
            "title": "6. Conclusion",
            "content": [
                "In this paper, we propose a universal guidance algorithm that is able to perform guided image generation with any off-theshelf guidance function based on a ﬁxed foundation diffusion model. Our algorithm only requires guidance and loss functions to be differentiable, and avoids any retraining to adapt either the guidance function or the foundation model to a speciﬁc type of prompt. We demonstrate promising results with our algorithm on complex guidance including segmentation, face recognition and object detection systems. Even multiple guidance functions can be combined and used in conjunction."
            ]
        },
        {
            "title": "7. Acknowledgements",
            "content": [
                "This work was made possible by the National Science Foundation (IIS-2212182), the AFOSR MURI Program, the Ofﬁce of Naval Research (N000142112557), the ONR MURI program, IARPA WRIVA, and Capital One Bank."
            ]
        },
        {
            "title": "References",
            "content": [
                "Austin, J., Johnson, D. D., Ho, J., Tarlow, D., and van den Berg, R. Structured denoising diffusion models in discrete state-spaces. Advances in Neural Information Processing Systems, 34:17981–17993, 2021.",
                "Bansal, A., Borgnia, E., Chu, H.-M., Li, J. S., Kazemi, H., Huang, F., Goldblum, M., Geiping, J., and Goldstein,",
                "T. Cold diffusion: Inverting arbitrary image transforms without noise. arXiv preprint arXiv:2208.09392, 2022.",
                "Chung, H., Kim, J., Mccann, M. T., Klasky, M. L., and Ye, J. C. Diffusion posterior sampling for general noisy inverse problems. arXiv preprint arXiv:2209.14687, 2022a.",
                "Chung, H., Sim, B., Ryu, D., and Ye, J. C. Improving diffusion models for inverse problems using manifold constraints. arXiv preprint arXiv:2206.00941, 2022b.",
                "Deng, J., Dong, W., Socher, R., Li, L.-J., Li, K., and Fei-Fei, L. Imagenet: A large-scale hierarchical image database. In 2009 IEEE conference on computer vision and pattern recognition, pp. 248–255. Ieee, 2009.",
                "Dhariwal, P. and Nichol, A. Q. Diffusion models beat gans on image synthesis. volume 34, 2021.",
                "Graikos, A., Malkin, N., Jojic, N., and Samaras, D. Diffusion models as plug-and-play priors. arXiv preprint arXiv:2206.09012, 2022.",
                "Ho, J. and Salimans, T. Classiﬁer-free diffusion guidance. arXiv preprint arXiv:2207.12598, 2022.",
                "Ho, J., Jain, A., and Abbeel, P. Denoising diffusion probabilistic models. Advances in Neural Information Processing Systems, 32, 2020.",
                "Howard, A., Sandler, M., Chu, G., Chen, L.-C., Chen, B., Tan, M., Wang, W., Zhu, Y., Pang, R., Vasudevan, V., et al. Searching for mobilenetv3. In Proceedings of the IEEE/CVF international conference on computer vision, pp. 1314–1324, 2019.",
                "Huang, R., Lam, M. W., Wang, J., Su, D., Yu, D., Ren, Y., and Zhao, Z. Fastdiff: A fast conditional diffusion model for high-quality speech synthesis. arXiv preprint arXiv:2204.09934, 2022.",
                "Kawar, B., Elad, M., Ermon, S., and Song, J. Denoising diffusion restoration models. arXiv preprint arXiv:2201.11793, 2022.",
                "Kong, Z., Ping, W., Huang, J., Zhao, K., and Catanzaro, B. Diffwave: A versatile diffusion model for audio synthesis. arXiv preprint arXiv:2009.09761, 2020.",
                "Li, X. L., Thickstun, J., Gulrajani, I., Liang, P., and Hashimoto, T. B. Diffusion-lm improves controllable text generation. arXiv preprint arXiv:2205.14217, 2022.",
                "Li, Y., Xie, S., Chen, X., Dollar, P., He, K., and Girshick, R. Benchmarking detection transfer learning with vision transformers. arXiv preprint arXiv:2111.11429, 2021.",
                "Lugmayr, A., Danelljan, M., Romero, A., Yu, F., Timofte, R., and Van Gool, L. Repaint: Inpainting using denoising diffusion probabilistic models. In Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition, pp. 11461–11471, 2022.",
                "Neubeck, A. and Van Gool, L. Efﬁcient non-maximum suppression. In 18th International Conference on Pattern Recognition (ICPR’06), volume 3, pp. 850–855. IEEE, 2006.",
                "Nichol, A., Dhariwal, P., Ramesh, A., Shyam, P., Mishkin, P., McGrew, B., Sutskever, I., and Chen, M. Glide: Towards photorealistic image generation and editing with text-guided diffusion models. arXiv preprint arXiv:2112.10741, 2021.",
                "Paszke, A., Gross, S., Massa, F., Lerer, A., Bradbury, J., Chanan, G., Killeen, T., Lin, Z., Gimelshein, N., Antiga, L., et al. Pytorch: An imperative style, high-performance deep learning library. Advances in neural information processing systems, 32, 2019.",
                "Radford, A., Kim, J. W., Hallacy, C., Ramesh, A., Goh, G., Agarwal, S., Sastry, G., Askell, A., Mishkin, P., Clark, J., et al. Learning transferable visual models from natural language supervision. In International Conference on Machine Learning, pp. 8748–8763. PMLR, 2021.",
                "Ren, S., He, K., Girshick, R., and Sun, J. Faster r-cnn: Towards real-time object detection with region proposal networks. Advances in neural information processing systems, 28, 2015.",
                "Rombach, R., Blattmann, A., Lorenz, D., Esser, P., and Ommer, B. High-resolution image synthesis with latent diffusion models. In Proceedings of CVPR, 2022.",
                "Schroff, F., Kalenichenko, D., and Philbin, J. Facenet: A uniﬁed embedding for face recognition and clustering. In Proceedings of the IEEE conference on computer vision and pattern recognition, pp. 815–823, 2015.",
                "Song, J., Meng, C., and Ermon, S. Denoising diffusion implicit models. International Conference on Learning Representations, 2021a.",
                "Song, Y. and Ermon, S. Generative modeling by estimating gradients of the data distribution. Advances in Neural Information Processing Systems, 32, 2019.",
                "Song, Y., Sohl-Dickstein, J., Kingma, D. P., Kumar, A., Ermon, S., and Poole, B. Score-based generative modeling through stochastic differential equations. International Conference on Learning Representations, 2021b.",
                "Wang, W., Bao, J., Zhou, W., Chen, D., Chen, D., Yuan, L., and Li, H. Semantic image synthesis via diffusion models. arXiv preprint arXiv:2207.00050, 2022a.",
                "Wang, Y., Yu, J., and Zhang, J. Zero-shot image restoration using denoising diffusion null-space model. arXiv preprint arXiv:2212.00490, 2022b.",
                "Whang, J., Delbracio, M., Talebi, H., Saharia, C., Dimakis, A. G., and Milanfar, P. Deblurring via stochastic reﬁnement. In Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition, pp. 16293– 16303, 2022.",
                "Zhang, K., Zhang, Z., Li, Z., and Qiao, Y. Joint face detection and alignment using multitask cascaded convolutional networks. IEEE signal processing letters, 23(10): 1499–1503, 2016."
            ]
        },
        {
            "title": "A. More results",
            "content": [
                "Figure 11: More images to show Segmentation guidance. In each subﬁgure, the ﬁrst image is the segmentation map used to guide the image generation with its caption as its text prompt.",
                "Figure 12: More images to show Face guidance. In each subﬁgure, the ﬁrst image is the human identity used to guide the image generation with its caption as its text prompt.",
                "Figure 13: More images to show Object Location guidance. In each subﬁgure, the ﬁrst image is the object location used to guide the image generation with its caption as its text prompt.",
                "Figure 14: More images to show Style Transfer. In each subﬁgure, the ﬁrst image is the styling image used to guide the image generation with its caption as its text prompt."
            ]
        }
    ]
    result = extract_core_sections(sections)
    # print(result.get("introduction", "N/A"), "\n\n-----------------------------------------\n\n")
    # print(result.get("method", "N/A"), "\n\n-----------------------------------------\n\n")
    # print(result.get("experiments", "N/A"), "\n\n-----------------------------------------\n\n")
    # print(result.get("conclusion", "N/A"), "\n\n-----------------------------------------\n\n")

    # test_cases = [
    #     "∗1Robin Rombach1 ∗",
    #     "∗∗Andreas Blattmann1 ∗",
    #     "——————Patrick Esser——————",
    #     "!@#Hello World!@#",
    #     "123Non-Alpha456",
    #     "∗∗∗123∗∗∗",
    #     "NoLettersHere123!@#"
    # ]
    #
    # for s in test_cases:
    #     print(f"原始: '{s}' → 清洗后: '{clean_text_both_sides(s)}'")
    #
    # test_cases = [
    #     "Robin Rombach1 ∗",  # True
    #     "Andreas Blattmann1 ∗",  # True
    #     "Patrick Esser——————",  # True
    #     "Dr. Watson",  # True ("Dr"和"Watson"都符合)
    #     "Jean-Pierre Dupont",  # True (会被分割为["Jean", "Pierre", "Dupont"])
    #     "McDonald's",  # False (分割后["McDonald", "s"] - "s"不符合)
    #     "e e cummings",  # False ("e"不符合首字母大写)
    #     "AL CAPONE",  # False ("AL"和"CAPONE"后续字母不是小写)
    #     "SingleWord",  # False (只有一个部分)
    #     "123 Name",  # False (分割后["Name"] - 只有一个部分)
    #     "No Letters Here!@#",  # True (分割后["No", "Letters", "Here"])
    #     "Dr. Jekyll and Mr. Hyde",  # True (多个部分都符合)
    #     "Mary-Kate Olsen",  # True (分割为["Mary", "Kate", "Olsen"])
    # ]
    #
    # for s in test_cases:
    #     print(f"'{s}': {extract_person_names(s)}")
    #
    #
    # print(len("Arpit Bansal * 1 Hong-Min Chu * 1 Avi Schwarzschild 1 Soumyadip Sengupta 2 Micah Goldblum 3 Jonas Geiping 1 Tom Goldstein 1"))

    # print(is_abstract("By decomposing the image formation process into a sequential application of denoising autoencoders, diffusion models (DMs) achieve state-of-the-art synthesis results on image data and beyond. Additionally, their formulation allows for a guiding mechanism to control the image generation process without retraining. However, since these models typically operate directly in pixel space, optimization of powerful DMs often consumes hundreds of GPU days and inference is expensive due to sequential evaluations. To enable DM training on limited computational resources while retaining their quality and ﬂexibility, we apply them in the latent space of powerful pretrained autoencoders. In contrast to previous work, training diffusion models on such a representation allows for the ﬁrst time to reach a near-optimal point between complexity reduction and detail preservation, greatly boosting visual ﬁdelity. By introducing cross-attention layers into the model architecture, we turn diffusion models into powerful and ﬂexible generators for general conditioning inputs such as text or bounding boxes and high-resolution synthesis becomes possible in a convolutional manner. Our latent diffusion models (LDMs) achieve new state of the art scores for image inpainting and class-conditional image synthesis and highly competitive performance on various tasks, including unconditional image generation, text-to-image synthesis, and super-resolution, while signiﬁcantly reducing computational requirements compared to pixel-based DMs."))

    # meta_dict = {
    #     'detection_class_prob': 0.7800827622413635,
    #     'coordinates': {
    #         'points': (
    #             (np.float64(152.60586547851562), np.float64(713.0761108398438)),
    #             (np.float64(152.60586547851562), np.float64(770.2613525390625)),
    #             (np.float64(796.4525146484375), np.float64(770.2613525390625)),
    #             (np.float64(796.4525146484375), np.float64(713.0761108398438))
    #         ),
    #         'system': 'PixelSpace',
    #         'layout_width': 1700, 'layout_height': 2200
    #     },
    #     'last_modified': '2025-07-15T19:45:18',
    #     'filetype': 'application/pdf',
    #     'languages': ['eng'],
    #     'page_number': 5,
    #     'filename': 'High-Resolution Image Synthesis with Latent Diffusion Models.pdf'
    # }
    #
    # output_img_path = "formulas/formula_5_001.png"
    #
    # extract_formula_image(
    #     pdf_path=meta_dict["filename"],
    #     page_number=meta_dict["page_number"],
    #     points=meta_dict["coordinates"]["points"],
    #     output_path=output_img_path
    # )

    # content = "40-50% masked All samples Method FID ↓ LPIPS ↓ FID ↓ LPIPS ↓ LDM-4 (ours, big, w/ ft) 9.39 0.246± 0.042 1.50 0.137± 0.080 LDM-4 (ours, big, w/o ft) 12.89 0.257± 0.047 2.40 0.142± 0.085 LDM-4 (ours, w/ attn) 11.87 0.257± 0.042 2.15 0.144± 0.084 LDM-4 (ours, w/o attn) 12.60 0.259± 0.041 2.37 0.145± 0.084 LaMa [85]† 12.31 0.243± 0.038 2.23 0.134± 0.080 LaMa [85] 12.0 0.24 2.21 0.14 CoModGAN [103] 10.4 0.26 1.82 0.15 RegionWise [51] 21.3 0.27 4.75 0.15 DeepFill v2 [100] 22.1 0.28 5.20 0.16 EdgeConnect [57] 30.5 0.28 8.37 0.16"
    # html = "<table><thead><tr><th rowspan=\"2\">Method</th><th colspan=\"2\">40-50% masked</th><th colspan=\"2\">All samples</th></tr><tr><th>FID |</th><th>LPIPS|</th><th>FIDJ</th><th>LPIPS |</th></tr></thead><tbody><tr><td>LDM-4 (ours, big, w/ ft)</td><td>9.39</td><td>0.246+ 0.042</td><td>1.50</td><td>— 0.137+ 0.080</td></tr><tr><td>LDM-4 (ours, big, w/o ft)</td><td>12.89</td><td>0.257+ 0.047</td><td>2.40</td><td>2+ 0.085</td></tr><tr><td>LDM-4 (ours, w/ attn)</td><td>11.87</td><td>0.257+ 0.042</td><td>2.15</td><td>0.144+ 0.084</td></tr><tr><td>LDM-4 (ours, w/o attn)</td><td>12.60</td><td>0.259+ 0.041</td><td>2.37</td><td>0.145+ 0.084</td></tr><tr><td>LaMa [85]*</td><td>12.31</td><td>0.2434 0.038</td><td>2.23,</td><td>0.134+ 0.080</td></tr><tr><td>LaMa [85]</td><td>12.0</td><td>0.24</td><td>2.21</td><td>0.14</td></tr><tr><td>CoModGAN [103]</td><td>10.4</td><td>0.26</td><td>1.82</td><td>0.15</td></tr><tr><td>RegionWise [51]</td><td>21.3</td><td>0.27</td><td>4.75</td><td>0.15</td></tr><tr><td>DeepFill v2 [100]</td><td>22.1</td><td>0.28</td><td>5.20</td><td>0.16</td></tr><tr><td>EdgeConnect [57]</td><td>30.5</td><td>0.28</td><td>8.37</td><td>0.16</td></tr></tbody></table>"
    #
    # result = extract_corrected_html_table_json(html, content)
    # print(json.dumps(result, indent=2, ensure_ascii=False))
    #
    #
    # print(len("By decomposing the image formation process into a se- quential application of denoising autoencoders, diffusion models (DMs) achieve state-of-the-art synthesis results on image data and beyond. Additionally, their formulation al- lows for a guiding mechanism to control the image gen- eration process without retraining. However, since these models typically operate directly in pixel space, optimiza- tion of powerful DMs often consumes hundreds of GPU days and inference is expensive due to sequential evalu- ations. To enable DM training on limited computational resources while retaining their quality and ﬂexibility, we apply them in the latent space of powerful pretrained au- toencoders. In contrast to previous work, training diffusion models on such a representation allows for the ﬁrst time to reach a near-optimal point between complexity reduc- tion and detail preservation, greatly boosting visual ﬁdelity. By introducing cross-attention layers into the model archi- tecture, we turn diffusion models into powerful and ﬂexi- ble generators for general conditioning inputs such as text or bounding boxes and high-resolution synthesis becomes possible in a convolutional manner. Our latent diffusion models (LDMs) achieve new state of the art scores for im- age inpainting and class-conditional image synthesis and highly competitive performance on various tasks, includ- ing unconditional image generation, text-to-image synthe- sis, and super-resolution, while signiﬁcantly reducing com- putational requirements compared to pixel-based DMs."))
    # print(len("Abstract. Weintroduce Recurrent All-Pairs Field Transforms (RAFT),a new deep network architecture for optical flow. RAFT extracts perpixel features, builds multi-scale 4D correlation volumes for all pairsof pixels, and iteratively updates a flow field through a recurrent unitthat performs lookups on the correlation volumes. RAFT achieves stateof-the-art performance. On KITTI, RAFT achieves an F1-all error of5.10%, a 16% error reduction from the best published result (6.10%).On Sintel (final pass), RAFT obtains an end-point-error of 2.855 pixels,a 30% error reduction from the best published result (4.098 pixels). Inaddition, RAFT has strong cross-dataset generalization as well as highefficiency in inference time, training speed, and parameter count. Codeis available at https://github.com/princeton-vl/RAFT."))
    # print(is_figure_caption("Figure 10"))
    # examples = [
    #     "2019 Z. Teed and J. Deng",  # ✅ True
    #     "[3] Deng, J., Dong, W., Socher, R.",  # ✅ True
    #     "ImageNet: A large-scale hierarchical...",  # ❌ False
    #     "J. Smith",  # ❌ False
    #     "Ruiz, Nataniel",  # ❌ False
    #     "A. Einstein. Relativity, 1916.",  # ❌ False
    #     "In: CVPR 2020"  # ✅ True（关键词）
    # ]
    #
    # for ex in examples:
    #     print(f"{repr(ex)} -> {is_reference_format(ex)}")
