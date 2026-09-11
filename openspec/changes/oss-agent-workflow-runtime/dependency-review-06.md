# AF06 DeepSeek exact dependency review

Status: AF06-D2 INSTALLATION VERIFIED; main-brain independently accepted dependency gate.
Existing64 packages are pinned in af06-installed-before.json and unchanged.
One approved mirror attempt; report and5 wheels retained only in task-owned temp.
Official PyPI version JSON was fetched per final artifact. Name/version/filename,
full SHA256, byte size and license matched; mirrors are not the trust anchor.

| New package | License | Bytes | SHA256 |
| --- | --- | ---: | --- |
| langchain-deepseek1.1.0 | MIT | 10061 | 14813cb413a97a5cce95118da253cfd64dce50537b7381b7c5d0ecf11d2a7032 |
| langchain-openai1.6.0 | MIT | 125078 | 648112bbd135aa51d60d4aa2fd4ad353628a8d92a2f8e779244a0d9869a16f18 |
| openai3.8.0 | Apache-2.0 | 1740349 | 514736aa1e4ef1033c1209ad53897392845ccd4f2c4fae6413b2cf5f91c2c926 |
| regex2026.9.3 | Apache-2.0 AND CNRI-Python | 801135 | 99034ec353c973e2c89555866083491b9a2dbe81f2fbe15fb0f2b68506232f01 |
| tiktoken0.14.0 | MIT | 1206378 | f5e7665f6624e052e5e7f6a36919ab69279decdc976d7b16b4fa15e1897d0513 |

Exact filenames:

- langchain_deepseek-1.1.0-py3-none-any.whl
- langchain_openai-1.6.0-py3-none-any.whl
- openai-3.8.0-py3-none-any.whl
- regex-2026.9.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
- tiktoken-0.14.0-cp311-cp311-manylinux_2_28_x86_64.whl

Dependency chain: langchain-deepseek -> langchain-openai -> openai/tiktoken;
tiktoken -> regex. All other requirements satisfied by unchanged existing64.
No Bailian/ChatQwen/json-repair candidate or additional provider dependency.

Official metadata:
[DeepSeek](https://pypi.org/pypi/langchain-deepseek/1.1.0/json),
[LangChain OpenAI](https://pypi.org/pypi/langchain-openai/1.6.0/json),
[OpenAI](https://pypi.org/pypi/openai/3.8.0/json),
[regex](https://pypi.org/pypi/regex/2026.9.3/json),
[tiktoken](https://pypi.org/pypi/tiktoken/0.14.0/json).

Wheelhouse: /home/admin/OpenSource/.tmp/af06-deepseek-wheels-EqxBQ8tA.
Proposed next operation, ONLY after exact main-brain approval: recheck these hashes,
install exact local wheels with --no-index --no-deps into existing project venv,
compare all64 prior versions, pip check and imports. No pip/system upgrade/global
configuration change/network model request is part of that proposed operation.

## AF06-D2 authorized installation

Main-brain independently checked official artifacts/not-yanked metadata, wheel hashes,
candidate requirements and no existing replacement before releasing exact5-wheel install.
Immediately before installation, all64 baseline versions and5 full hashes matched again.
Installed only5 exact local paths with existing venv python -m pip install --no-index
--no-deps --disable-pip-version-check. After:69 unique distributions, only approved5
new entries, every existing64 name/version unchanged. pip check: no broken requirements.
All5 imports resolve under project venv lib64/python3.11/site-packages. No system or pip
upgrade, extra download, real provider request or credential lookup.
