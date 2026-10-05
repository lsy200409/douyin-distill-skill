"""faster-whisper 批量中文转写。默认优先用 GPU(CUDA float16)，无 GPU 回退 CPU int8。
强制输出简体中文（用 initial_prompt 引导，避免繁体字）。"""
import os
from pathlib import Path

# 引导 faster-whisper 输出简体中文而非繁体
ZH_SIMPLIFIED_PROMPT = "以下是普通话简体中文语音的转写，请只用简体中文输出，不要使用繁体字。"


def _resolve_device(device: str) -> tuple[str, str]:
    """根据配置决定 device 与 compute_type：cuda→float16，cpu→int8。"""
    if device == 'cuda':
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                return 'cuda', 'float16'
        except Exception:
            pass
        print('未检测到可用 CUDA，回退 CPU')
        return 'cpu', 'int8'
    return 'cpu', 'int8'


def _load_model(model_size: str, device: str = 'cuda'):
    from faster_whisper import WhisperModel
    dev, ctype = _resolve_device(device)
    print(f'转写设备: {dev} / {ctype}')
    return WhisperModel(model_size, device=dev, compute_type=ctype)


def transcribe_file(whisper_model, mp3_file: str, transcript_dir: str,
                    lang: str = 'zh', initial_prompt: str = ZH_SIMPLIFIED_PROMPT) -> Path:
    Path(transcript_dir).mkdir(parents=True, exist_ok=True)
    out = Path(transcript_dir) / (Path(mp3_file).stem + '.txt')
    segs, _ = whisper_model.transcribe(mp3_file, language=lang, initial_prompt=initial_prompt)
    text = ''.join(s.text for s in segs)
    out.write_text(text, encoding='utf-8')
    return out


def transcribe_all(audio_dir: str, transcript_dir: str, model_size: str = 'small',
                   device: str = 'cuda') -> int:
    files = sorted(Path(audio_dir).glob('*.mp3'))
    if not files:
        print(f'无 mp3 可转写: {audio_dir}')
        return 0
    model = _load_model(model_size, device)
    count = 0
    for f in files:
        out = Path(transcript_dir) / (f.stem + '.txt')
        if out.exists():
            print(f'跳过已转写: {f.name}')
            continue
        print(f'转写: {f.name}')
        transcribe_file(model, str(f), transcript_dir)
        count += 1
    return count


def transcribe_one(mp3_file: str, transcript_dir: str, model_size: str = 'small',
                   device: str = 'cuda') -> Path:
    model = _load_model(model_size, device)
    return transcribe_file(model, mp3_file, transcript_dir)


def transcribe_one_reuse(model, mp3_file: str, transcript_dir: str) -> Path:
    """复用已加载的 whisper 模型转写单个 mp3（流式/批内增量用）。"""
    return transcribe_file(model, mp3_file, transcript_dir)
