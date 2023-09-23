from services.jobs.fetch.base import DataController
from services.lib.date_utils import format_time_ago, now_ts, MINUTE, seconds_human
from services.lib.depcont import DepContainer
from services.lib.http_ses import ObservableSession, RequestEntry
from services.lib.money import format_percent, short_address
from services.lib.texts import bold, code, pre, ital, link


class AdminMessages:
    def __init__(self, d: DepContainer):
        self.deps = d
        self.creation_timestamp = now_ts()

    @property
    def uptime(self):
        return format_time_ago(now_ts() - self.creation_timestamp)

    async def get_debug_message_text_fetcher(self):
        message = '⚙️' + bold('Debug info') + '\n\n'

        data_ctrl: DataController = self.deps.pool_fetcher.data_controller

        for name, fetcher in data_ctrl.summary.items():
            if fetcher.success_rate < 90.0:
                errors = f'❌︎ {fetcher.error_counter} errors'
            else:
                errors = '🆗 No errors' if not fetcher.error_counter else f'🆗︎ {fetcher.error_counter} errors'

            last_ts = fetcher.last_timestamp
            sec_elapsed = now_ts() - last_ts
            last_txt = format_time_ago(sec_elapsed)
            if sec_elapsed > 10 * MINUTE:
                last_txt += '❗'

            interval = seconds_human(fetcher.sleep_period)
            success_rate_txt = format_percent(fetcher.success_rate, 100.0)

            if fetcher.total_ticks > 0:
                ticks_str = fetcher.total_ticks
            else:
                ticks_str = '🤷 none yet!'

            message += (
                f"{code(name)}\n"
                f"{errors}. "
                f"Last date: {ital(last_txt)}. "
                f"Interval: {ital(interval)}. "
                f"Success rate: {pre(success_rate_txt)}. "
                f"Total ticks: {ticks_str}"
                f"\n\n"
            )

        if not data_ctrl.summary:
            message += 'No info'

        message += f'\n<b>Uptime:</b> {self.uptime}'

        return message

    async def get_debug_message_text_session(self, start=0, count=10, rps=True):
        message = f'🕸️ {bold("HTTP session info")}\n\n'

        # noinspection PyTypeChecker
        session: ObservableSession = self.deps.session

        now = now_ts()

        top_requests = session.debug_top_calls(start + count + 1)
        for i, item in enumerate(top_requests[start:start + count], start=(start + 1)):
            item: RequestEntry

            med_t = item.avg_time.median
            max_t = item.avg_time.max
            avg_t = item.avg_time.average

            last_ago = format_time_ago(now - item.last_timestamp)
            if item.response_codes:
                code_txt = ' | '.join(f'{bold(k)}: {v}' for k, v in item.response_codes.items())
            else:
                code_txt = 'No response yet'
            caption = short_address(item.url, 40, 80)
            message += (
                f'{i}. {link(item.url, caption)}\n'
                f'{bold(item.total_calls)} calls | {bold(item.total_errors)} err | {last_ago}\n'
                f'Med <b>{med_t:.1f}</b>, avg <b>{avg_t:.1f}</b>, max <b>{max_t:.1f}</b>\n'
                f'Codes: {code_txt}'
            )
            if item.none_count:
                message += f' | None: {item.none_count}'
            if item.text_answer_count:
                message += f' | T: {item.text_answer_count}, last: {pre(item.last_text_answer)}'

            message += '\n\n'

        if rps:
            message += f'<b>RPS:</b> {session.rps:.2f} req/sec'

        return message

    @staticmethod
    def text_bot_restarted():
        return '🤖 Bot restarted!'
