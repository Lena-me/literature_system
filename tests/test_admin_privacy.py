from app.utils.admin_privacy import (
    mask_email,
    mask_head_tail,
    mask_phone,
    mask_paper_filename,
    mask_username,
    sanitize_technical_error_log,
)


def test_mask_paper_filename():
    assert mask_paper_filename('Attention.pdf') == mask_head_tail('Attention', head=3, tail=2) + '.pdf'
    masked = mask_paper_filename('AttentionIsAllYouNeed.pdf')
    assert masked.startswith('Att')
    assert masked.endswith('.pdf')
    assert '****' in masked


def test_mask_username():
    assert mask_username('123') == '用户****'
    assert mask_username('alice') == 'al··e'


def test_redact_paper_id_in_error():
    raw = 'ValueError: paper 18 has been deleted'
    out = sanitize_technical_error_log(raw)
    assert out is not None
    assert '18' not in out
    assert 'paper' not in out.lower()
    assert 'ValueError' in out


def test_mask_phone():
    assert mask_phone('13812345678') == '138****5678'


def test_mask_email():
    out = mask_email('user@example.com')
    assert '@' in out
    assert '****' in out or '***' in out


def test_sanitize_celery_error():
    raw = 'TimeoutError: connection to mineru timed out after 120s'
    assert sanitize_technical_error_log(raw) == raw


def test_sanitize_user_prose():
    prose = 'Research on Multimodal Medical Image Segmentation Algorithms for Ovarian Cancer'
    out = sanitize_technical_error_log(prose)
    assert out == 'ProcessingError'
    assert 'Ovarian' not in (out or '')


def test_sanitize_traceback():
    raw = '''Traceback (most recent call last):
  File "/app/workers/tasks.py", line 10, in run
    raise ValueError("bad chunk")
ValueError: bad chunk'''
    out = sanitize_technical_error_log(raw)
    assert out is not None
    assert 'ValueError' in out
    assert 'tasks.py' in out or 'bad chunk' in out
