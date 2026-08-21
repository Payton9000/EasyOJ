"""竞赛相关的工具函数"""


def calculate_penalty(submissions_for_problem, contest_start_time):
    """计算某用户在某题的罚时

    Args:
        submissions_for_problem: 该用户对某题的所有提交列表（应已按时间排序）
        contest_start_time: 比赛开始时间

    Returns:
        {
            'status': 'AC'|'WA'|None,
            'attempts': int,
            'ac_time': int（分钟）或None,
            'penalty': int（分钟）
        }
    """
    if not submissions_for_problem:
        return {'status': None, 'attempts': 0, 'ac_time': None, 'penalty': 0}

    status = None
    attempts = len(submissions_for_problem)
    ac_time = None
    penalty = 0

    # 找第一个AC
    ac_submission = None
    for s in submissions_for_problem:
        if s.status == 'AC':
            ac_submission = s
            break

    if ac_submission:
        status = 'AC'
        # 计算AC时间（距比赛开始的分钟数）
        ac_time = int((ac_submission.submitted_at - contest_start_time).total_seconds() / 60)

        # 计算罚时：AC前的WA次数 * 20
        wa_before_ac = sum(
            1
            for s in submissions_for_problem
            if s.submitted_at < ac_submission.submitted_at and s.status != 'AC'
        )
        penalty = ac_time + wa_before_ac * 20
    else:
        # 没有AC，有其他提交
        status = 'WA'
        penalty = 0

    return {'status': status, 'attempts': attempts, 'ac_time': ac_time, 'penalty': penalty}


def format_duration(minutes):
    """将分钟数格式化为可读字符串

    Args:
        minutes: 分钟数（整数）

    Returns:
        格式化的字符串，如 "2h 5m" 或 "45m"
    """
    if minutes <= 0:
        return '0m'

    hours = minutes // 60
    mins = minutes % 60

    if hours == 0:
        return f'{mins}m'
    elif mins == 0:
        return f'{hours}h'
    else:
        return f'{hours}h {mins}m'
