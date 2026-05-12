from adapter.middleware import Middleware
from monitor.base_monitor import BaseMonitor, RoleType


def _extract_original_content(ctx):
    if ctx.args and len(ctx.args) > 0:
        messages = ctx.args[0]
        if messages and isinstance(messages, list) and len(messages) > 0:
            last_msg = messages[-1]
            if isinstance(last_msg, dict) and 'content' in last_msg:
                return last_msg['content']
    elif 'messages' in ctx.kwargs:
        messages = ctx.kwargs['messages']
        if messages and isinstance(messages, list) and len(messages) > 0:
            last_msg = messages[-1]
            if isinstance(last_msg, dict) and 'content' in last_msg:
                return last_msg['content']
    return ""


class ThinkMiddleware(Middleware):

    def __init__(self, monitor: BaseMonitor, name: str):
        self.monitor = monitor
        self.name = name

    def before(self, ctx):
        if not self.monitor:
            return None
        if hasattr(self.monitor, 'should_inject') and self.monitor.should_inject():
            if hasattr(self.monitor, 'is_injected') and not self.monitor.is_injected():
                original_content = _extract_original_content(ctx)
                if hasattr(self.monitor, 'inject_content'):
                    injected_content = self.monitor.inject_content(original_content)
                    return injected_content
        return None

    def after(self, ctx, result):
        if not self.monitor:
            return result

        if hasattr(self.monitor, 'record_step'):
            self.monitor.record_step(result, self.name, RoleType.ASSISTANT)

        return result

