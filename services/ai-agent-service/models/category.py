from enum import Enum

class Category(str, Enum):
    SECURITY = "Security"
    PERFORMANCE = "Performance"
    CODE_QUALITY = "Code Quality"
    API = "API"
    DATABASE = "Database"
    DEVOPS = "DevOps"
    INFRASTRUCTURE = "Infrastructure"
    DOCUMENTATION = "Documentation"
    TESTING = "Testing"
    ARCHITECTURE = "Architecture"
    TRADING = "Trading"
    