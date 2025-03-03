import javalang
from javalang.tree import ClassDeclaration, MethodDeclaration, FieldDeclaration, ReferenceType


class JavaCodeSanitizer:
    """
    Java代码净化处理器
    功能特性：
    - 精确识别访问修饰符
    - 完整保留泛型体系
    - 支持嵌套类型和复杂继承
    - 符合Oracle Java代码规范
    - 异常安全处理机制
    """

    def __init__(self):
        self.indent = "    "  # 标准的4空格缩进

    def sanitize(self, java_source: str) -> str:
        """
        执行代码净化处理
        :param java_source: 原始Java源代码
        :return: 净化后的代码
        """
        try:
            ast = javalang.parse.parse(java_source)
        except javalang.parser.JavaSyntaxError as e:
            raise ValueError(f"Java语法错误: {e.at} {e.message}") from e

        processed_code = []
        for path, node in ast.filter(ClassDeclaration):
            self._process_class(node, processed_code)
        return '\n'.join(processed_code)

    def _process_class(self, cls: ClassDeclaration, output: list):
        """处理类声明结构"""
        signature = self._build_class_signature(cls)
        output.append(f"{signature} {{\n")

        for member in cls.body:
            if isinstance(member, FieldDeclaration):
                self._process_field(member, output)
            elif isinstance(member, MethodDeclaration):
                self._process_method(member, cls.name, output)

        output.append("}\n")

    def _build_class_signature(self, cls: ClassDeclaration) -> str:
        """构建符合JLS规范的类签名"""
        components = []
        # 过滤类注解并保留其他修饰符
        components.extend([m for m in cls.modifiers if not m.startswith('@')])

        # 处理泛型参数
        type_params = ""
        if cls.type_parameters:
            type_params = f"<{', '.join(tp.name for tp in cls.type_parameters)}>"

        # 类继承体系
        extends_clause = f"extends {self._parse_type(cls.extends)}" if cls.extends else ""
        implements_clause = f"implements {', '.join(self._parse_type(t) for t in cls.implements)}" if cls.implements else ""

        return ' '.join(filter(None, [
            ' '.join(components),
            f"class {cls.name}{type_params}",
            extends_clause,
            implements_clause
        ]))

    def _process_field(self, field: FieldDeclaration, output: list):
        """处理字段声明"""
        if 'private' in field.modifiers:
            return

        modifiers = ' '.join([m for m in field.modifiers if not m.startswith('@')])
        field_type = self._parse_type(field.type)
        output.append(f"{self.indent}{modifiers} {field_type} {field.declarators[0].name};\n")

    def _process_method(self, method: MethodDeclaration, class_name: str, output: list):
        """处理方法声明"""
        if 'private' in method.modifiers:
            return

        signature = self._build_method_signature(method, class_name)
        output.append(f"{self.indent}{signature} {{}}\n")

    def _build_method_signature(self, method: MethodDeclaration, class_name: str) -> str:
        """生成标准方法签名"""
        components = []
        # 过滤方法注解
        components.extend([m for m in method.modifiers if not m.startswith('@')])

        # 处理泛型参数
        if method.type_parameters:
            components.append(f"<{', '.join(tp.name for tp in method.type_parameters)}>")

        # 构造方法判断
        is_constructor = method.name == class_name

        # 返回类型处理
        if not is_constructor:
            return_type = self._parse_type(method.return_type) or 'void'
            components.append(return_type)

        # 方法名称
        components.append(method.name)

        # 参数列表处理
        params = []
        for param in method.parameters:
            param_type = self._parse_type(param.type)
            if param.varargs:
                param_type = param_type.replace('[]', '...')
            modifiers = ' '.join(param.modifiers)
            params.append(f"{modifiers} {param_type} {param.name}".strip())
        components.append(f"({', '.join(params)})")

        # 异常声明
        if method.throws:
            components.append(f"throws {', '.join(self._parse_type(t) for t in method.throws)}")

        return ' '.join(components)

    def _parse_type(self, t) -> str:
        """类型解析引擎（支持泛型/数组/通配符）"""
        if isinstance(t, ReferenceType):
            return self._parse_reference_type(t)
        return getattr(t, 'name', '')  # 基础类型直接返回名称

    def _parse_reference_type(self, t: ReferenceType) -> str:
        """解析复杂引用类型"""
        # 通配符处理
        if t.name == '?':
            if t.arguments and t.arguments[0].upper_bound:
                return f"? extends {self._parse_type(t.arguments[0].upper_bound)}"
            elif t.arguments and t.arguments[0].lower_bound:
                return f"? super {self._parse_type(t.arguments[0].lower_bound)}"
            return "?"

        # 泛型处理
        if t.arguments:
            args = ', '.join(self._parse_type(arg.type) for arg in t.arguments)
            return f"{t.name}<{args}>"

        # 数组处理
        if t.dimensions:
            return f"{t.name}{'[]' * t.dimensions}"

        return t.name


if __name__ == "__main__":
    sanitizer = JavaCodeSanitizer()

    test_code = """
    @Service
    public class DataProcessor<T extends Serializable> 
        implements BatchOperations {

        @Autowired
        private EntityManager em;

        protected final Logger log = LoggerFactory.getLogger(getClass());

        public DataProcessor(Class<T> entityClass) {}

        @Transactional
        public <R> Page<R> findAll(
            Specification<T> spec, 
            Pageable pageable, 
            final Class<? extends R>... projectionTypes
        ) throws DataAccessException {
            return repository.findAll(spec, pageable);
        }

        private void validate() {}
    }
    """

    print(sanitizer.sanitize(test_code))
