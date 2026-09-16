from utils import *

# 主程序执行
if __name__ == "__main__":
    img_path = "test_img/G14.png"  # 梯子图图片路径
    file_path = "test_img/纸联III堤坝洪流&自治筛分·梯子图DMT坐标编码表v1.1.xlsx" # Excel配置文件路径
    json_file = "test_img/纸联III堤坝洪流&自治筛分·梯子图DMT坐标编码表v1.1.json" # JSON配置文件路径
    split_img_dir = "test_img/split_img"  # 分割图片输出目录
    output_file = "test_img/G14梯子图DMT解析结果.json"  # 输出结果文件路径
    # 进行DMT分析
    results = analyze_dmt_region(
        img_path=img_path,
        file_path=file_path,
        json_file=json_file,
        split_img_dir=split_img_dir,
        output_file=output_file
    )
    print("DMT版面分析全部完成！")

