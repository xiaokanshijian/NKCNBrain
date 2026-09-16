import os

if __name__ == '__main__':
    sceneDirPath = '../received_dir/' + 'scene_excel/' + '大文件9'
    print(sceneDirPath)
    # bookList=[]
    filesList = []
    if os.path.exists(sceneDirPath):
        files_and_dirs = os.listdir(sceneDirPath)
        for file in files_and_dirs:
            if os.path.isfile(os.path.join(sceneDirPath, file)):
                if file.endswith(".xlsx"):
                    continue
                filesList.append(file)
    print(filesList)