import os
import re
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import javalang
from javalang.tree import MethodDeclaration, FieldDeclaration, ClassDeclaration
from source_cut import JavaCodeSanitizer

PROCYON_CMD = "procyon"
OUTPUT_DIR = "./source_collection"
CUSTOM_REPO = "/Users/cyc/Documents/repo/lib"
CLS_REP = "/Users/cyc/class_repo"
TARGET_PACKAGES = ("com.aidc", "com.alibaba","com.alibaba.fastjson")


class MavenMultiModule:
    def __init__(self, project_root):
        self.root = project_root
        self.start_module = self.find_start_module()
        self.all_modules = self.find_all_modules()

    def find_start_module(self):
        """查找以 -start 结尾的主模块"""
        for root, dirs, _ in os.walk(self.root):
            if root.endswith("-start") and 'pom.xml' in os.listdir(root):
                return root
        raise Exception("未找到以 -start 结尾的主模块")

    def find_all_modules(self):
        """查找所有子模块的源码目录"""
        modules = []
        for root, _, files in os.walk(self.root):
            if 'pom.xml' in files:
                src_path = os.path.join(root, "src/main/java")
                if os.path.exists(src_path):
                    modules.append(src_path)
        return modules

    def get_project_dependencies(self):
        """在主模块获取全量依赖"""
        result = subprocess.run(
            ["mvn", "dependency:tree", "-Dverbose"],
            cwd=self.start_module,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception(f"依赖解析失败:\n{result.stderr}")

        return self.parse_dependency_output(result.stdout)

    def parse_dependency_line(self,line):
        """通过冒号分割解析依赖行"""
        if not line.strip().startswith("[INFO]"):
            return None

        # 移除前缀符号和空格
        clean_line = line.split("+- ")[-1].split("\\- ")[-1].strip()

        # 分割关键字段
        parts = clean_line.split(":")
        if len(parts) < 5:
            return None

        # 提取基础信息
        group_id = parts[0]
        artifact_id = parts[1]
        version = parts[3]

        # 处理scope中的括号说明
        scope_part = parts[4].split(" ")[0]  # 取第一个单词作为scope
        scope = scope_part.split("(")[0] if "(" in scope_part else scope_part

        # 过滤无效版本
        if "${" in version or not version:
            return None

        return (group_id, artifact_id, version)

    def parse_dependency_output(self,output):
        """解析整个依赖树输出"""
        deps = set()
        for line in output.split('\n'):
            # 跳过非依赖行
            if "[INFO] ---" in line or "BUILD" in line:
                continue

            result = self.parse_dependency_line(line)
            if result:
                deps.add(result)

        return list(deps)


class SourceScanner:
    def __init__(self, project):
        self.project = project
        self.scanned_jars = 0
        self.total_jars = 0

    def is_target_package(self, class_fqn):
        """检查是否是目标包"""
        return class_fqn.startswith(TARGET_PACKAGES)

    def find_source(self, target_class):
        """查找类来源"""
        # 在项目模块中查找
        java_path = target_class.replace('.', '/') + ".java"
        code_san = JavaCodeSanitizer()
        for module_src in self.project.all_modules:
            full_path = os.path.join(module_src, java_path)
            if os.path.exists(full_path):
                with open(full_path, 'r') as f:
                    if "CapacityAlgorithmInvokeProcessor" in full_path:
                        return {
                            "type": "project",
                            "content": f.read(),
                            "path": full_path
                        }
                    else:
                        return {
                        "type": "project",
                        "content": code_san.sanitize(f.read()),
                        "path": full_path
                    }

        # 在依赖中查找
        return self.find_in_dependencies(target_class)

    def find_in_dependencies(self, target_class):
        """在依赖中查找并反编译"""
        if not self.is_target_package(target_class):
            print(f"跳过非目标包类: {target_class}")
            return None

        class_file = target_class.replace('.', '/') + ".class"
        dependencies = self.project.get_project_dependencies()
        self.total_jars = len(dependencies)

        print(f"开始扫描 {self.total_jars} 个依赖JAR包...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for dep in dependencies:
                jar_path = self.build_jar_path(dep)
                futures.append(executor.submit(
                    self.check_jar,
                    jar_path, class_file, target_class
                ))

            # 进度跟踪
            for future in as_completed(futures):
                result = future.result()
                self.scanned_jars += 1
                self.print_progress(start_time)
                if result:
                    executor.shutdown(wait=False)
                    for f in futures:
                        f.cancel()
                    return result

        return None

    def build_jar_path(self, dep):
        """构建JAR包路径"""
        group, artifact, version = dep
        dir = group.replace(".","/")
        return os.path.join(
            f"{CUSTOM_REPO}/{dir}/{artifact}/{version}",
            f"{artifact}-{version}.jar"
        )

    def print_progress(self, start_time):
        """打印扫描进度"""
        elapsed = time.time() - start_time
        speed = self.scanned_jars / elapsed if elapsed > 0 else 0
        print(f"\r扫描进度: {self.scanned_jars}/{self.total_jars} | "
              f"完成: {self.scanned_jars / self.total_jars:.1%} | "
              f"速度: {speed:.1f}个/秒", end="")

    @staticmethod
    def check_jar(jar_path, class_file, class_fqn):
        """检查单个JAR包"""
        try:
            if not os.path.exists(jar_path):
                return None

            with zipfile.ZipFile(jar_path, 'r') as zf:
                if class_file not in zf.namelist():
                    return None

                print(f"\n发现目标类在: {os.path.basename(jar_path)}")
                subprocess.run(
                    f"unzip -o {jar_path} {class_file} -d {CLS_REP}",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                result = subprocess.run(
                    f"java -jar /Users/cyc/PycharmProjects/extractSourceNew/procyon.jar {CLS_REP}/{class_file}",
                    shell=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    return {
                        "type": "decompiled",
                        "content": result.stdout,
                        "path": jar_path
                    }
        except Exception as e:
            print(f"\n处理 {jar_path} 失败: {str(e)}")
        return None


class CodeAnalyzer:
    @staticmethod
    def get_referenced_classes(source_code):
        """获取直接引用的类"""
        imports = re.findall(r'^import\s+([\w.]+?)(?:\.\*)?;', source_code, re.M)
        return list(set(imports))


def main(target_class, project_root):
    # 初始化项目
    project = MavenMultiModule(project_root)
    scanner = SourceScanner(project)

    # 收集目标类源码
    target_source = scanner.find_source(target_class)
    if not target_source:
        print(f"未找到类 {target_class}")
        return

    print(f"\n找到目标类来源: {target_source['path']}")

    # 收集引用类
    analyzer = CodeAnalyzer()
    referenced = analyzer.get_referenced_classes(target_source["content"])
    print(f"发现直接引用类 {len(referenced)} 个")

    # 收集所有源码
    source_map = {target_class: target_source["content"]}
    for i, cls in enumerate(referenced, 1):
        print(f"正在处理引用类 ({i}/{len(referenced)}): {cls}")
        source = scanner.find_source(cls)
        if source:
            source_map[cls] = source["content"]

    # 生成输出文件
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"{target_class.replace('.', '_')}_sources.java")

    with open(output_file, 'w') as f:
        for cls, code in source_map.items():
            f.write(f"// ==== Source: {cls} ====\n")
            f.write(code)
            f.write("\n\n")

    print(f"\n生成成功！输出文件位置: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("用法: python3 maven_scanner.py <全限定类名> <项目根目录>")
        sys.exit(1)

    try:
        main(sys.argv[1], sys.argv[2])
    except Exception as e:
        print(f"\n错误: {str(e)}")
        sys.exit(1)
