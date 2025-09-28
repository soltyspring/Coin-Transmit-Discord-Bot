@echo off
REM === Python 실행해서 최신 airdrop_explorers.json 생성 ===
python Z:\dev\coin\Notice_Explorers.py

REM === SCP로 서버에 업로드 ===
scp -i "C:\Users\aghose\.ssh\ssh-key-2025-09-27.key" airdrop_explorers.json ubuntu@129.154.56.88:/home/ubuntu/Coin-Transmit-Discord-Bot/

echo =======================================
echo ✅ 업로드 완료! 서버에서 discord_coin.py가 자동으로 읽습니다.
pause
