import structlog

structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
