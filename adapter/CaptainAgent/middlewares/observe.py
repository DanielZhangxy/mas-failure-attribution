from adapter.middleware import Middleware
from monitor.base_monitor import BaseMonitor


class ObserveMiddleware(Middleware):

    def __init__(self, monitor: BaseMonitor):
        self.monitor = monitor

    def after(self, ctx, result):
        if not self.monitor:
            return result
        instance = ctx.instance
        if hasattr(instance, 'chat_messages'):
            for other_agent, messages in instance.chat_messages.items():
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        sender = last_msg.get("name", "unknown")
                        content = last_msg.get("content", "")
                        if hasattr(self.monitor, 'record_topology'):
                            self.monitor.record_topology(sender, instance.name)

        return result