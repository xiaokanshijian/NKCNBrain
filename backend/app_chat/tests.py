from django.test import TestCase

# Create your tests here.
from django.test import TestCase

# Create your tests here.
import jieba
import networkx as nx
import numpy as np
import re

import re
import jieba


zzq = "路上只我一个人，背着手踱着。这一片天地好像是我的;我也像超出了平常旳自己，到了另一世界里。我\
爱热闹，也爱冷静;爱群居，也爱独处。像今晚上，一个人在这苍茫旳月下，什么都可以想，什么都可以\
不想，便觉是个自由的人。白天里一定要做的事，一定要说的话，现在都可不理。这是独处的妙处，我\
且受用这无边的荷香月色好了。曲曲折折的荷塘上面，弥望旳是田田的叶子。叶子出水很高，像亭亭旳\
舞女旳裙。层层的叶子中间，零星地点缀着些白花，有袅娜(niǎo,nuó)地开着旳，有羞涩地打着朵儿旳;正\
如一粒粒的明珠，又如碧天里的星星，又如刚出浴的美人。微风过处，送来缕缕清香，仿佛远处高楼上\
渺茫的歌声似的。这时候叶子与花也有一丝的颤动，像闪电般，霎时传过荷塘的那边去了。叶子本是肩\
并肩密密地挨着，这便宛然有了一道凝碧的波痕。叶子底下是脉脉(mò)的流水，遮住了，不能见一些颜\
色;而叶子却更见风致了。月光如流水一般，静静地泻在这一片叶子和花上。薄薄的青雾浮起在荷塘里。\
叶子和花仿佛在牛乳中洗过一样;又像笼着轻纱的梦。虽然是满月，天上却有一层淡淡的云，所以不能朗\
照;但我以为这恰是到了好处——酣眠固不可少，小睡也别有风味的。月光是隔了树照过来的，高处丛生\
的灌木，落下参差的斑驳的黑影，峭楞楞如鬼一般;弯弯的杨柳的稀疏的倩影，却又像是画在荷叶上。塘\
中的月色并不均匀;但光与影有着和谐的旋律，如梵婀(ē)玲(英语violin小提琴的译音)上奏着的名曲。荷塘\
的四面，远远近近，高高低低都是树，而杨柳最多。这些树将一片荷塘重重围住;只在小路一旁，漏着几\
段空隙，像是特为月光留下的。树色一例是阴阴的，乍看像一团烟雾;但杨柳的丰姿，便在烟雾里也辨得\
出。树梢上隐隐约约的是一带远山，只有些大意罢了。树缝里也漏着一两点路灯光，没精打采的，是渴\
睡人的眼。这时候最热闹的，要数树上的蝉声与水里的蛙声;但热闹是它们的，我什么也没有。"

def chinese_word_cut(text):
    # CSDN：《文本分析-使用jieba库进行中文分词和去除停用词（附案例实战）》
    # jieba.load_userdict('自定义词典.txt')  # 这里你可以添加jieba库识别不了的网络新词，避免将一些新词拆开
    jieba.initialize()  # 初始化jieba
    # 文本预处理 ：去除一些无用的字符只提取出中文出来
    new_data = re.findall('[\u4e00-\u9fa5]+', text, re.S)
    new_data = " ".join(new_data)
    # 文本分词
    seg_list_exact = jieba.lcut(new_data)
    result_list = []
    # 读取停用词库
    with open('stopWord.txt', encoding='utf-8') as f:  # 可根据需要打开停用词库，然后加上不想显示的词语:https://github.com/XinyaoTian/stopwords/tree/master
        con = f.readlines()
        stop_words = set()
        for i in con:
            i = i.replace("\n", "")  # 去掉读取每一行数据的\n
            stop_words.add(i)
    # 去除停用词并且去除单字
    for word in seg_list_exact:
        if word not in stop_words and len(word) > 1:
            result_list.append(word)
    return result_list


def get_graph(words):
    G = nx.Graph()
    # 添加节点和边
    for word in words:
        G.add_node(word)
    for i in range(len(words) - 1):
        G.add_edge(words[i], words[i + 1])
    # 去除孤立节点
    G.remove_nodes_from(list(nx.isolates(G)))
    return G

# TextRank算法
def textrank(G, lower=True, weight='weight', max_iter=100):
    # [未用]获取TextRank得分最高的关键词
    # pagerank_scores = textrank(G)
    if lower:
        words = [word.lower() for word in G]
    else:
        words = G
    M = nx.to_numpy_matrix(G)
    n = M.shape[0]
    # 初始化pagerank值
    pagerank = dict(zip(words, [1.0 / n] * n))
    # 迭代计算
    for _ in range(max_iter):
        new_pagerank = np.zeros(n)
        for i in range(n):
            for j in range(n):
                if M[i, j] != 0:
                    new_pagerank[j] += pagerank[i] / M.sum(axis=1)[i]
        pagerank = new_pagerank

    # 归一化 PageRank 值
    sum_pr = np.sum(pagerank.values())
    pagerank = {word: pr / sum_pr for word, pr in pagerank.items()}

    return pagerank


def get_topk_from_text(text, topk):
    words = chinese_word_cut(text)
    G = get_graph(words)
    # params: {G, alpha=0.85, personalization=None, max_iter=100, tol=1.0e-6, nstart=None, weight="weight", dangling=None)
    pagerank_scores = nx.pagerank(G=G, max_iter=200)
    sorted_pagerank = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)
    word_list = []
    score_list = []
    for word, score in sorted_pagerank[:topk]:
        word_list.append(word)
        score_list.append(score)
    return word_list, score_list


def get_topk_from_histroy(username, chat_history):
    user_history = chat_history[username]
    print(user_history)
    return "11111"

if __name__ == '__main__':
    words, _ = get_topk_from_text(zzq, 20)
    print(words)
