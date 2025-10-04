class ChaInfo:
    # 类变量（只初始化一次，所有实例共享）
    shared_data = None
    initialized = False

    @classmethod
    def init(cls, data={}):
        """初始化方法，确保只执行一次"""
        if not cls.initialized:
            cls.shared_data = data
            cls.initialized = True

    @classmethod
    def get_data(cls):
        """获取共享数据的类方法"""
        return cls.shared_data
    
    @classmethod
    def set_char_data(cls, kingdom, index, data):
        # 确保kingdom层级存在
        if kingdom not in cls.shared_data:
            cls.shared_data[kingdom] = {}
        
        # 确保index层级存在
        if index not in cls.shared_data[kingdom]:
            cls.shared_data[kingdom][index] = {}
        
        # 对每个slot进行逐个处理：存在则更新，不存在则添加
        for key, value in data.items():
            cls.shared_data[kingdom][index][key] = value
        
        
    @classmethod
    def get_char_data(cls, kingdom='', index='', key=''):
        if key:
            return cls.shared_data[kingdom][index][key]
        elif index:
            return cls.shared_data[kingdom][index]
        elif kingdom:
            return cls.shared_data[kingdom]
        else:
            return cls.shared_data