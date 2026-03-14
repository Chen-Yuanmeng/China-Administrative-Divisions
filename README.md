# 中国行政区划数据 (省/市/区县/乡镇 四级)

本项目采取与 [modood/Administrative-divisions-of-China](https://github.com/modood/Administrative-divisions-of-China) 项目类似的数据组织形式。

原项目依据2023年版本的行政规划制作，至今部分数据由于行政区划变更导致已过时，且由于行政区划信息的发布已由国家统计局转为民政部，导致原项目代码无法继续使用。为此，本项目重新依据民政部官方提供的接口重写了数据爬取和处理的代码。

## 数据来源

1. 中国大陆的数据来源为民政部 [中国·国家地名信息库](https://dmfw.mca.gov.cn/index.html) 提供的行政区划搜索接口服务 (接口文档见 https://dmfw.mca.gov.cn/interface.html)
2. 香港特别行政区、澳门特别行政区和台湾省的数据来源综合了维基百科（[香港行政区划](https://zh.wikipedia.org/zh-cn/%E9%A6%99%E6%B8%AF%E8%A1%8C%E6%94%BF%E5%8D%80%E5%8A%83)、[澳门行政区划](https://zh.wikipedia.org/zh-cn/%E6%BE%B3%E9%96%80%E8%A1%8C%E6%94%BF%E5%8D%80%E5%8A%83)）、百度百科（[台湾省](https://baike.baidu.com/item/%E5%8F%B0%E6%B9%BE%E7%9C%81/761219#2)）、淘宝收货地址中的添加地址功能（可登录淘宝后访问[收货地址](https://member1.taobao.com/member/fresh/deliver_address.htm)页面）等多个来源的数据进行整理和补充。

## 文件列表

以下所有文件放在 dist 目录下

1. 单级数据

| 文件列表                     | JSON | CSV |
|:-----------------------------|:-----|:----|
| 省级（省份、直辖市、自治区） | [provinces.json](./dist/provinces.json) | [provinces.csv](./dist/provinces.csv) |
| 地级（城市）                 | [cities.json](./dist/cities.json) | [cities.csv](./dist/cities.csv) |
| 县级（区县）                 | [areas.json](./dist/areas.json) | [areas.csv](./dist/areas.csv) |
| 乡级（乡镇、街道）           | [streets.json](./dist/streets.json) | [streets.csv](./dist/streets.csv) |

2. 各级联动数据

| 文件列表                                    | 普通 | 带编码 |
|:--------------------------------------------|:-----|:-------|
| “省份、城市” 二级联动数据                   | [pc.json](./dist/pc.json) | [pc-code.json](./dist/pc-code.json) |
| “省份、城市、区县” 三级联动数据             | [pca.json](./dist/pca.json) | [pca-code.json](./dist/pca-code.json) |
| “省份、城市、区县、乡镇” 四级联动数据       | [pcas.json](./dist/pcas.json) | [pcas-code.json](./dist/pcas-code.json) |

3. 人工整理的港澳台数据: [HK-MO-TW.json](./dist/HK-MO-TW.json)

**省级数据预览**

| code | name           |
|:-----|:---------------|
| 13   | 河北省         |
| 14   | 山西省         |
| 15   | 内蒙古自治区    |
| 45   | 广西壮族自治区  |

**地级数据预览**

| code | name       | provinceCode |
|:-----|:-----------|:-------------|
| 1301 | 石家庄市   | 13           |
| 1401 | 太原市     | 14           |
| 1525 | 锡林郭勒盟 | 15           |
| 4503 | 桂林市     | 45           |

**县级数据预览**

| code   | name     | cityCode | provinceCode |
|:-------|:---------|:---------|:-------------|
| 130111 | 栾城区   | 1301     | 13           |
| 140121 | 清徐县   | 1401     | 14           |
| 152527 | 太仆寺旗 | 1525     | 15           |
| 450305 | 七星区   | 4503     | 45           |

**乡级数据预览**

| code      | name           | areaCode | cityCode | provinceCode |
|:----------|:---------------|:---------|:---------|:-------------|
| 130111200 | 南高乡         | 130111   | 1301     | 13           |
| 140121102 | 东于镇         | 140121   | 1401     | 14           |
| 152527201 | 贡宝拉格苏木   | 152527   | 1525     | 15           |
| 450305004 | 漓东街道       | 450305   | 4503     | 45           |


## Q&A

1. 为什么没有港澳台的数据？

    港澳台的数据不在[中国·国家地名信息库](https://dmfw.mca.gov.cn/index.html) 提供的行政区划搜索接口服务 (接口文档见 https://dmfw.mca.gov.cn/interface.html) 中提供，因此需要人工整理。人工整理的数据见 [HK-MO-TW.json](./dist/HK-MO-TW.json)。

2. 为什么广东省东莞市、广东省中山市、海南省儋州市、甘肃省嘉峪关市下面一个区县都没有？

    全国现有4个不设区地级市，分别是：广东省东莞市、中山市，海南省儋州市，甘肃省嘉峪关市。具体可参考 [不设区的市 - 百度百科](https://baike.baidu.com/item/%E4%B8%8D%E8%AE%BE%E5%8C%BA%E7%9A%84%E5%B8%82/6990731) 对这些市，使用市名作为区县一级的占位符。

3. 我希望获得村镇一级的数据，能否提供？

    目前国家地名信息库提供的接口服务只提供了省/市/区县/乡镇 四级的数据，因此无法获得村镇一级的数据。

    参考项目（[modood/Administrative-divisions-of-China](https://github.com/modood/Administrative-divisions-of-China)）中有村镇一级的数据，但其指向的数据来源已不可用，因此无法继续更新维护。

    如果你有官方渠道的村镇数据来源，欢迎提供给我，我可以考虑更新数据爬取和处理的代码以获得村镇一级的数据。

4. 我想获取历史数据，怎么办？

    请更改代码中请求参数中的 year 字段，如下：
    ```python
    class McaClient:
        ...

        def get_children(self, code: str, max_level: int = 1) -> List[ApiNode]:
            params = {"code": code, "maxLevel": max_level}
            # params 中添加 year 参数可获取对应年份的历史数据，不加默认为最新数据
            # 如 params = {"code": code, "maxLevel": max_level, "year": 2020}  # 获取2020年版本的行政区划数据

            ...
    ```

5. 我想获取更详细的数据（如行政区划的经纬度信息），怎么办？

    请自行查看其他来源的数据，如 [高德地图开放平台](https://lbs.amap.com/api/webservice/guide/api/district) 提供的行政区划查询接口服务等。

6. 我需要 SQL 版本的数据，如何获取？

    请自行运行程序，数据库文件会生成在 [checkpoints/top4.sqlite](./checkpoints/top4.sqlite) 处。

## 许可证

本项目的代码部分采用 MIT 许可证，数据部分采用 CC0 1.0 许可证，详见 [LICENSE](./LICENSE) 文件。
