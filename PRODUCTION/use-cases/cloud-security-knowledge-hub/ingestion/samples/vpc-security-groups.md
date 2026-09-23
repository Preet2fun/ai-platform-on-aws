# VPC Security Groups and Network Segmentation

## Secure configuration
Security groups are stateful virtual firewalls attached to ENIs. Allow only the specific
inbound ports and source ranges each workload needs. Reference other security groups as the
source instead of CIDR ranges for internal traffic, so rules follow the workload rather than
IP addresses. Keep management ports (SSH 22, RDP 3389) closed to the internet; use SSM Session
Manager for shell access instead.

## How an attack happens
An overly permissive rule such as `0.0.0.0/0` on port 22, 3389, or a database port lets
attackers reach the service directly. Automated bots continuously scan for open SSH/RDP and
database ports, then attempt brute force or exploit known CVEs.

## Prevention
- Never open SSH/RDP/database ports to 0.0.0.0/0; restrict to a bastion SG or VPN CIDR.
- Use SG-to-SG references for tiered access (web SG -> app SG -> db SG).
- Layer NACLs for subnet-level deny rules and defense in depth.
- Use VPC endpoints so traffic to AWS services stays off the public internet.
- Enable VPC Flow Logs and alert on denied or unexpected connections.

## Verification
Audit for any SG rule allowing 0.0.0.0/0 on 22/3389/3306/5432, and confirm Flow Logs are on.
