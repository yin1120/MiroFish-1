import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('140.138.175.53', port=22, username='r70640', password='r70604', timeout=10)

commands = [
    # 1. 備份 unit 檔
    "cp ~/.config/systemd/user/lab-engine.service ~/.config/systemd/user/lab-engine.service.bak",
    # 2. 寫入 PYTORCH_CUDA_ALLOC_CONF
    "grep -q 'PYTORCH_CUDA_ALLOC_CONF' ~/.config/systemd/user/lab-engine.service || sed -i '/Environment=\"MODEL_PATH/i Environment=\"PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True\"' ~/.config/systemd/user/lab-engine.service",
    # 3. 檢查修改結果
    "cat ~/.config/systemd/user/lab-engine.service",
    # 4. 重新載入並重啟引擎
    "systemctl --user daemon-reload",
    "systemctl --user restart lab-engine.service"
]

for cmd in commands:
    print(f">>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    if out:
        print(out.strip())
    if err:
        print(f"ERR: {err.strip()}")

print("\nWaiting 20 seconds for model to reload...")
time.sleep(20)

stdin, stdout, stderr = ssh.exec_command("tail -n 25 /mnt/r70640/logs/engine.log")
print(stdout.read().decode('utf-8', errors='ignore'))

ssh.close()
