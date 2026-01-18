docker --version | Out-File -FilePath docker_check.txt -Encoding ascii
docker-compose --version | Out-File -FilePath docker_check.txt -Append -Encoding ascii
Get-Command docker | Out-File -FilePath docker_check.txt -Append -Encoding ascii
