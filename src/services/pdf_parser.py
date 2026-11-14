import os
import json
from typing import Dict, List, Any
from datetime import datetime
from unstructured.partition.pdf import partition_pdf
from services.tools import *

from configs import DATA_DIR
OUTPUT_BASE_DIR = os.path.join(DATA_DIR, "parsed_results")
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

class PDFParser:
    def __init__(self):
        pass

    def parse_pdf(self, paper_id: int, file_path: str) -> Dict[str, Any]:
        """
        解析PDF文件，提取结构化信息
        """

        print("[PARSER] 正在解析PDF……")

        try:
            # OUTPUT_DIR = f"./data/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            OUTPUT_DIR = os.path.join(OUTPUT_BASE_DIR, f"paper_{paper_id}")
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            # 使用unstructured解析PDF
            elements = partition_pdf(
                filename=file_path,
                strategy="hi_res",  # 高分辨率策略，更好地识别表格和图像
                infer_table_structure=True,  # 推断表格结构
                extract_images_in_pdf=True,  # 提取图像
                extract_image_block_types=["Image", "Table"],  # 提取图像和表格
                extract_image_block_output_dir=os.path.join(OUTPUT_DIR, "figures"),
                extract_image_block_to_payload=False,
                languages=["eng", "equ"]
            )

            # 初始化结果字典
            result = {
                "title": "",
                "authors": [],
                "sources": [],
                "abstract": "",
                "sections": [],
                "tables": [],
                "images": [],
                "formulas": [],
                "references": [],
                "unstructured": [],
                "full_text": ""
            }

            # 分析元素
            current_section = None
            full_text_parts = []

            for idx, element in enumerate(elements):
                element_type = str(type(element).__name__)
                text = element.text.strip().replace('- ', '').replace('ﬁ','fi') if hasattr(element, 'text') else ""

                # 添加到全文
                # full_text_parts.append(text)

                # 根据元素类型进行分类
                if element_type == "Title":
                    if len(text)>100:
                        result["authors"].extend(extract_person_names(text))
                    if not result["title"]:  # 第一个标题作为论文标题
                        result["title"] = text
                    else:  # 其他标题作为章节标题
                        current_section = {
                            "title": text,
                            "content": []
                        }
                        result["sections"].append(current_section)
                    full_text_parts.append(f"[Title]{text}")

                elif element_type == "Text":
                    if not current_section:
                        if not result["sections"]:
                            result["sections"].append({
                                "title": "PreInfo",
                                "content": []
                            })
                            current_section = result["sections"][0]
                    if current_section["title"] == "PreInfo":
                        current_section["content"].append(text)
                    else:
                        result["unstructured"].append(text)
                        full_text_parts.append(f"[UnstructuredText]{text}")


                elif element_type == "NarrativeText":
                    if is_abstract(text):
                        result["abstract"] = text
                    if current_section:
                        current_section["content"].append(text)
                    else:
                        # 如果没有当前章节，创建一个默认章节
                        if not result["sections"]:
                            result["sections"].append({
                                "title": "PreInfo",
                                "content": []
                            })
                            current_section = result["sections"][0]
                        current_section["content"].append(text)
                        full_text_parts.append(f"[Title]PreInfo")
                    full_text_parts.append(f"{text}")


                elif element_type == "ListItem":
                    if current_section:
                        current_section["content"].append(text)
                    if is_reference_format(text):
                        result["references"].append(text)
                    full_text_parts.append(f"· {text}")

                elif element_type == "Image":
                    image_dict = element.metadata.to_dict() if hasattr(element, 'metadata') else {}
                    image_data = {
                        "caption": "",
                        "image_path": image_dict["image_path"],
                        "page_number": image_dict["page_number"],
                        "coordinates": image_dict["coordinates"],
                    }
                    # 优先向下找
                    found = False
                    for offset in range(1, len(elements) - idx):
                        next_el = elements[idx + offset]
                        next_type = str(type(next_el).__name__)
                        if next_type == "Image":
                            continue  # 连续的 Image 都跳过
                        next_text = getattr(next_el, "text", "")
                        if next_type in ["FigureCaption", "NarrativeText"] and is_figure_caption(next_text):
                            image_data['caption'] = next_text
                            found = True
                        break  # 只看遇到的第一个非 Image 元素

                    # 如果向下没找到或没命中，再向上找
                    if not found:
                        for offset in range(1, idx + 1):
                            prev_el = elements[idx - offset]
                            prev_type = str(type(prev_el).__name__)
                            if prev_type == "Image":
                                continue  # 连续的 Image 也跳过
                            prev_text = getattr(prev_el, "text", "")
                            if prev_type in ["FigureCaption", "NarrativeText"] and is_figure_caption(prev_text):
                                image_data['caption'] = prev_text
                            break  # 只检查第一个非 Image 元素

                    result["images"].append(image_data)
                    full_text_parts.append(f"[Image]{image_data['caption']}({image_data['image_path']})")


                elif element_type == "Table":
                    table_dict = element.metadata.to_dict() if hasattr(element, 'metadata') else {}
                    table_data = {
                        "caption": "",
                        "image_path": table_dict["image_path"],
                        "page_number": table_dict["page_number"],
                        "coordinates": table_dict["coordinates"],
                        "content": extract_corrected_html_table_json(table_dict["text_as_html"],
                                                                     getattr(element, "content", ""))
                    }

                    # 优先向下找
                    found = False
                    for offset in range(1, len(elements) - idx):
                        next_el = elements[idx + offset]
                        next_type = str(type(next_el).__name__)
                        if next_type == "Table":
                            continue  # 连续的 Image 都跳过
                        next_text = getattr(next_el, "text", "")
                        if next_type in ["FigureCaption", "NarrativeText"] and is_figure_caption(next_text):
                            table_data['caption'] = next_text
                            found = True
                        break  # 只看遇到的第一个非 Image 元素

                    # 如果向下没找到或没命中，再向上找
                    if not found:
                        for offset in range(1, idx + 1):
                            prev_el = elements[idx - offset]
                            prev_type = str(type(prev_el).__name__)
                            if prev_type == "Table":
                                continue
                            prev_text = getattr(prev_el, "text", "")
                            if prev_type in ["FigureCaption", "NarrativeText"] and is_figure_caption(prev_text):
                                table_data['caption'] = prev_text
                            break

                    result["tables"].append(table_data)
                    full_text_parts.append(f"[Table]{table_data['caption']}({table_data['image_path']})")


                elif element_type == "Formula":
                    formula_dict = element.metadata.to_dict() if hasattr(element, 'metadata') else {}
                    output_path = f'{OUTPUT_DIR}/formulas/formula_{formula_dict["page_number"]}_{extract_formula_number(text)}_{generate_unique_id()}.png'
                    extract_formula_image(
                        file_path,
                        formula_dict["page_number"],
                        formula_dict["coordinates"]["points"],
                        output_path=output_path,
                    )

                    formula_data = {
                        "image_path": output_path,
                        "page_number": formula_dict["page_number"],
                        "coordinates": formula_dict["coordinates"],
                        "content": text
                    }

                    result["formulas"].append(formula_data)
                    full_text_parts.append(f"[Formula]{text}({output_path})")

            # 设置全文
            result["full_text"] = "\n\n".join(full_text_parts)

            # 后处理
            if not result["title"]:
                result["title"] = os.path.basename(file_path).replace('.pdf', '')

            for section in result["sections"]:
                if section["title"].lower() == "abstract":
                    result["abstract"] = "\n".join(section["content"])
                if section["title"] == "PreInfo":
                    for text in section["content"]:
                        result["sources"].extend(extract_https_urls(text))
                        if len(text) < 200:
                            result["authors"].extend(extract_person_names(text))

            if len(result["references"]) < 10:
                for section in result["sections"]:
                    if section["title"].lower() == "references":
                        result["references"] = section["content"]

            print(f"[PARSER] PDF解析完毕: {len(full_text_parts)} 个DOM, {len(result['full_text'])} 字符")
            safe_title = result["title"].strip().replace(' ', '_').replace('/', '_').replace(':', '_').replace('"',
                                                                                                               '').replace(
                '*', '').replace('?', '').replace('<', '').replace('>', '').replace('|', '').replace('-', '_')
            save_path = os.path.join(OUTPUT_DIR, f"{safe_title}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"[PARSER] 解析结果 result 已写入 {save_path}")

            return result

        except Exception as e:
            raise Exception(f"PDF parsing failed: {str(e)}")


if __name__ == '__main__':
    parser = PDFParser()
    # _ = parser.parse_pdf("./High-Resolution Image Synthesis with Latent Diffusion Models.pdf")
    # _ = parser.parse_pdf("./RAFT_Recurrent All-Pairs Field Transforms for Optical Flow.pdf")
    _ = parser.parse_pdf("./Universal Guidance for Diffusion Models.pdf")
