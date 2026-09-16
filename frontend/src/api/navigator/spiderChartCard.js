// id: Dom 元素 id, e.g. "#someChart";
// axes: 指标数组列表; e.g. ["Weight", "Height"];
// data: 数据列表（可能多组）; e.g. [[12.0, 0.5], [12.1, 0.7]];
// options: 与下面的 var cfg 相同的格式配置对象;
// onEdit: 拖动结束时将调用的回调函数;
export function SpiderChartCard(id, axes, data, options, timeModel) {
    const model_count = data.length;
    var cfg = {
        w: 300, // Width
        h: 300, // Height
        margin: {top: 60, right: 60, bottom: 60, left: 60},
        levels: 5,                      // 分级数
        maxValue: 1.0,                  // 最外层所表示的值
        labelPositionRatio: 1.2,        // 表示轴的标签相对于最外层水平从中心到中心的距离
        textWrapWidth: 60,              // 需要为标签指定新行的最大宽度
        areaOpacity: 0.35,              // 数据覆盖区域的不透明度
        vertexRadius: 6,                // 顶点的大小
        backgroundOpacity: 0.1,         // 背景的不透明度
        strokeWidth: 2,                 // 数据覆盖区域的描边宽度
        color: d3.scale.category10()    // 数据区域颜色
    };
    // 按传入更新配置 cfg
    if ('undefined' !== typeof options) {
        for (var i in options) {
            if ('undefined' !== typeof options[i]) {
                cfg[i] = options[i];
            }
        }
    }

    // 为每个指标定义最小和最大值（改）
    const axisMinAndMaxGPT4 = [
        { min: 0.05, max: 2.0 },
        { min: 0.05, max: 0.95 },
        { min: -2.0, max: 2.0 },
        { min: -2.0, max: 2.0 },
        { min: 512, max: 8192 },
        { min: 1, max: 3}
    ];

    const axisMinAndMaxMixtral = [
        { min: 0.05, max: 2.0 },
        { min: 0.05, max: 0.95 },
        { min: 10, max: 100 },
        { min: 512, max: 8192 },
        { min: 0, max: 1 },
        { min: 1, max: 20 },
        { min: 1, max: 20 },
        { min: 1, max: 3 },
        { min: 0, max: 5 },
        { min: 512, max: 8192 },
        { min: -2, max: 2 },
        { min: -2, max: 2 }
    ];

    const axisMinAndMaxKimi = [
        { min: 0.05, max: 1.0 },
        { min: 0.05, max: 0.95 },
        { min: -2.0, max: 2.0 },
        { min: -2.0, max: 2.0 },
        { min: 512, max: 8192 },
        { min: 1, max: 3}
    ];

    const axisMinAndMaxLlama = [
        { min: 0.05, max: 1.0 },
        { min: 0.05, max: 0.95 },
        { min: -2.0, max: 2.0 },
        { min: -2.0, max: 2.0 },
        { min: 512, max: 8192 }
    ];

    const axisMinAndMaxClaude = [
        { min: 0.05, max: 1.0 },
        { min: 0.05, max: 0.95 },
        { min: 15, max: 50 },
        { min: 512, max: 8192 }
    ];

    const axisMinAndMaxDeepseek = [
        { min: 0.05, max: 2.0 },
        { min: 0.05, max: 0.95 },
        { min: -2.0, max: 2.0 },
        { min: -2.0, max: 2.0 },
        { min: 512, max: 8192 }
    ];

    function reverseConvert(value, index) {
        if(timeModel === 'GPT4') {
            let range = axisMinAndMaxGPT4[index];
            return value * (range.max - range.min) + range.min;
        } else if(timeModel === 'Mixtral') {
            let range = axisMinAndMaxMixtral[index];
            return value * (range.max - range.min) + range.min;
        } else if(timeModel === 'Kimi') {
            let range = axisMinAndMaxKimi[index];
            return value * (range.max - range.min) + range.min;
        } else if(timeModel === 'llama3') {
            let range = axisMinAndMaxLlama[index];
            return value * (range.max - range.min) + range.min;
        } else if(timeModel === 'Deepseek') {
            let range = axisMinAndMaxDeepseek[index];
            return value * (range.max - range.min) + range.min;
        } else {
            let range = axisMinAndMaxClaude[index];
            return value * (range.max - range.min) + range.min;
        }
    }

    var maxAxisValues = [];
    var radius = Math.min(cfg.w / 2, cfg.h / 2);	 	      // 最外层圆的半径
    var FormatValue = d3.format('%');		 	              // 按百分比格式显示
    var angleSlice = Math.PI * 2 / axes.length;		          // 每个指标“切片”的弧度（角）

    // 从数据值缩放到半径
    var rScale = d3.scale.linear()
        .range([0, radius])
        .domain([0, cfg.maxValue]);
    // 更新比例尺(改)
    // var rScales = axes.map((axis, i) => {
    //     return d3.scale.linear()
    //         .range([0, radius])
    //         .domain([axisMinAndMax[i].min, axisMinAndMax[i].max]);
    // });

    // 删除之前存在的任何具有相同 id/类的图表
    d3.select(id).select("svg").remove();

    // 初始化蜘蛛图的 SVG
    var svg = d3.select(id).append("svg")
        .attr("width", cfg.w + cfg.margin.left + cfg.margin.right)
        .attr("height", cfg.h + cfg.margin.top + cfg.margin.bottom)
        .attr("class", "spider" + id);
    // 添加一个 g 元素，创建一个新的图形组，并将这个组移动到SVG画布的中心位置
    var g = svg.append("g")
        .attr("transform", "translate(" + (cfg.w / 2 + cfg.margin.left) + "," + (cfg.h / 2 + cfg.margin.top) + ")");

    // 创建了一个名为 glow 的过滤器，它首先对图像进行高斯模糊处理，然后将其与原始图像合并，从而创建出一种发光效果
    var filter = g.append('defs').append('filter').attr('id', 'glow'),
        feGaussianBlur = filter.append('feGaussianBlur').attr('stdDeviation', '2.5').attr('result', 'coloredBlur'),
        feMerge = filter.append('feMerge'),
        feMergeNode_1 = feMerge.append('feMergeNode').attr('in', 'coloredBlur'),
        feMergeNode_2 = feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    // 根据每个指标的值和轴的角度来绘制出雷达图的多边形闭合区域
    var spiderLine = d3.svg.line.radial()
        .interpolate("linear-closed")
        .radius(function (d) {
            return rScale(d);
        })
        .angle(function (d, i) {
            return i * angleSlice;
        });

    // 将用来包含所有的轴网格相关元素，如轴线、刻度线、标签等
    var axisGrid = g.append("g").attr("class", "axisWrapper");

    // 创建一系列逐渐减小的同心多边形环，作为背景网格
    var web = [];
    for (let i = cfg.levels; i > 0; i--) {
        let c = [];
        for (let j = 0; j < axes.length; j++) {
            c.push(cfg.maxValue * i / cfg.levels);
        }
        web.push(c);
    }
    axisGrid.selectAll(".levels")
        .data(web)
        .enter()
        .append("path")
        .attr("d", function (d, i) {
            return spiderLine(d);
        })
        .attr("class", "web")
        .style("stroke", "grey")
        .style("stroke-opacity", function (d, i) {
            return i==0?1.0:0.5;
        })
        .style("stroke-width", "1px")
        .style("fill", "none");

    // 每个层级对应的轴标签，位置、样式和文本，标识每层的数值范围，#737373 是深灰色。
    axisGrid.selectAll(".axisLabel")
        .data(d3.range(1, (cfg.levels + 1)).reverse())
        .enter().append("text")
        .attr("class", "axisLabel")
        .attr("x", 4)
        .attr("y", function (d) {
            return -d * radius / cfg.levels;
        })
        .attr("dy", "0.4em")
        .style("font-size", "10px")
        .attr("fill", "#737373")
        .text(function (d, i) {
            return FormatValue(cfg.maxValue * d / cfg.levels);
        });

    // 初始化轴
    var axis = axisGrid.selectAll(".axis")
        .data(axes)
        .enter()
        .append("g")
        .attr("class", "axis");
    // 为每个轴创建一条从中心点出发到外围对应位置的直线，颜色和宽度
    axis.append("line")
        .attr("x1", 0)
        .attr("y1", 0)
        .attr("x2", function (d, i) {
            maxAxisValues[i] = {x: rScale(cfg.maxValue) * Math.cos(angleSlice * i - Math.PI / 2), y: 0};
            return maxAxisValues[i].x;
        })
        .attr("y2", function (d, i) {
            maxAxisValues[i].y = rScale(cfg.maxValue) * Math.sin(angleSlice * i - Math.PI / 2);
            return maxAxisValues[i].y
        })
        .attr("class", "line")
        .style("stroke", "#EEEEEE")
        .style("stroke-width", "2px");

    // 在每个轴上附加标签
    axis.append("text")
        .attr("class", "legend")
        .style("font-size", "11px")
        .attr("text-anchor", "middle")
        .attr("dy", "0.35em")
        .attr("x", function (d, i) {
            return maxAxisValues[i].x * cfg.labelPositionRatio;
        })
        .attr("y", function (d, i) {
            return maxAxisValues[i].y * cfg.labelPositionRatio;
        })
        .text(function (d) {
            return d
        })
        .call(wrapLongText, cfg.textWrapWidth);

    // 包装数据
    var modelWrapper = g.selectAll(".spiderWrapper")
        .data(data)
        .enter().append("g")
        .attr("class", "spiderWrapper");

    // 初始化雷达图区
    modelWrapper
        .append("path")
        .attr("class", "spiderArea")
        .attr("d", function (d, i) {
            return spiderLine(d);
        })
        .attr("id", function (d, i) {
            return "spiderArea" + i;
        })
        .style("fill", function (d, i) {
            return cfg.color(i);
        })
        .style("fill-opacity", cfg.areaOpacity)
        .on('mouseover', function (d, i) {
            // 鼠标悬浮区域高光
            d3.selectAll(".spiderArea")
                .transition().duration(200)
                .style("fill-opacity", 0.1);
            d3.select(this)
                .transition().duration(200)
                .style("fill-opacity", 0.7);
        })
        .on('mouseout', function () {
            // 鼠标移开恢复
            d3.selectAll(".spiderArea")
                .transition().duration(200)
                .style("fill-opacity", cfg.areaOpacity);
        });

    // 初始化连线
    modelWrapper.append("path")
        .attr("class", "spiderStroke")
        .attr("d", function (d, i) {
            return spiderLine(d);
        })
        .attr("id", function (d, i) {
            return "spiderStroke" + i;
        })
        .style("stroke-width", cfg.strokeWidth + "px")
        .style("stroke", function (d, i) {
            return cfg.color(i);
        })
        .style("fill", "none")
        .style("filter", "url(#glow)");


    // 鼠标悬停文本提示
    var tooltip = g.append("text")
        .attr("class", "tooltip")
        .style("opacity", 0);


    // 蜘蛛图的顶点和交互效果
    modelWrapper.selectAll(".spiderVertex")
        .data(function (d, i) {
            return d;
        })
        .enter().append("circle")
        .attr("class", "spiderVertex")
        .attr("r", cfg.vertexRadius)
        .attr("cx", function (d, i) {
            return rScale(d) * Math.cos(angleSlice * i - Math.PI / 2);
        })
        .attr("cy", function (d, i) {
            return rScale(d) * Math.sin(angleSlice * i - Math.PI / 2);
        })
        .style("fill", function (d, i, j) {
            return cfg.color(j);
        })
        .style("fill-opacity", 0.8)
        .style("pointer-events", "all")
        .on("mouseover", function (d, i) {
            let newX = parseFloat(d3.select(this).attr('cx')) - 10;
            let newY = parseFloat(d3.select(this).attr('cy')) - 10;
            tooltip
                .attr('x', newX)
                .attr('y', newY)
                .text(reverseConvert(d, i).toFixed(1))
                .transition().duration(200)
                .style('opacity', 1);
        })
        .on("mouseout", function () {
            tooltip.transition().duration(200)
                .style("opacity", 0);
        })
        .style("cursor", "pointer")


    // SVG中过长文本需要换行
    function wrapLongText(dom, width) {
        dom.each(function () {
            var text = d3.select(this),
                words = text.text().split(/\s+/).reverse(),
                word,
                line = [],
                lineNumber = 0,
                lineHeight = 1.4,
                y = text.attr("y"),
                x = text.attr("x"),
                dy = parseFloat(text.attr("dy")),
                tspan = text.text(null).append("tspan").attr("x", x).attr("y", y).attr("dy", dy + "em");

            while (word = words.pop()) {
                line.push(word);
                tspan.text(line.join(" "));
                if (tspan.node().getComputedTextLength() > width) {
                    line.pop();
                    if (line.length == 0) {
                        word = ""
                    } else {
                        tspan.text(line.join(" "));
                        line = [word];
                    }
                    tspan = text.append("tspan").attr("x", x).attr("y", y).attr("dy", ++lineNumber * lineHeight + dy + "em").text(word);
                }
            }
        });
    }

}