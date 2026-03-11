# exporter.py
import pandas as pd
from typing import List, Dict, Any
import io

def generate_excel(data: List[Dict[str, Any]]) -> io.BytesIO:
    formatted_data = []
    for index, row in enumerate(data, start=1):
        new_row: Dict[str, Any] = {"№": index}
        for k, v in row.items():
            if pd.isna(v) if isinstance(v, float) else False:
                new_row[k] = ""
            elif isinstance(v, (int, float)):
                # Форматируем число без 'E': до 8 знаков после запятой, отсекаем лишние нули
                s = f"{v:.8f}".rstrip('0').rstrip('.')
                new_row[k] = s if s else "0"
            else:
                new_row[k] = str(v)
        formatted_data.append(new_row)
        
    df = pd.DataFrame(formatted_data)
    output = io.BytesIO()
    # Use pandas to write to BytesIO
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Summaries')
        
        # Получаем доступ к листу через openpyxl
        worksheet = writer.sheets['Summaries']
        
        # Определяем базовые значения для визуального масштаба.
        # Стандартная ширина колонки в Excel около 8.43, высота строки 15.
        # Стандартный размер шрифта - 11.
        # Текущий базовый масштаб был 1.66. 
        # Высоту оставляем х2 (3.32).
        # Ширину и шрифт немного уменьшаем до 1.8 и делаем меньше отступов, чтобы влезло в экран.
        width_scale = 1.7
        height_scale = 3.32
        font_scale = 1.7  # Шрифт увеличиваем вместе с шириной, чтобы текст влезал
        
        base_width = 8.43 * width_scale
        base_height = 15 * height_scale
        
        # Увеличиваем размер шрифта
        from openpyxl.styles import Font
        huge_font = Font(size=11 * font_scale)
        
        # Меняем высоту всех строк, где есть данные (и заголовков тоже)
        for row_idx, row in enumerate(worksheet.iter_rows()):
            # openpyxl нумерует строки с 1
            worksheet.row_dimensions[row_idx + 1].height = base_height
            
            # Меняем шрифт для каждой ячейки
            for cell in row:
                cell.font = huge_font

        # Растягиваем ширину колонок пропорционально их содержимому, умноженному на фактор
        for column_cells in worksheet.columns:
            # Если это первая колонка ("№"), задаём ей фиксированную ширину 5
            if column_cells[0].value == "№":
                worksheet.column_dimensions[column_cells[0].column_letter].width = 5 * width_scale
            else:
                # Находим самую длинную строку в колонке (в символах)
                length = max(len(str(cell.value)) for cell in column_cells)
                # Устанавливаем ширину колонки: длина текста * фактор масштабирования + минимальный запас
                worksheet.column_dimensions[column_cells[0].column_letter].width = (length + 1.5) * width_scale
        
    output.seek(0)
    return output
