# Amazon EKS Cluster Security

## Secure configuration
Lock down the EKS control plane endpoint: prefer private endpoint access, or restrict public
access to known CIDRs. Use IAM Roles for Service Accounts (IRSA) or EKS Pod Identity so pods get
scoped, short-lived AWS credentials instead of node-role permissions. Apply Kubernetes RBAC with
least privilege and enable audit logging to CloudWatch.

## How an attack happens
A pod that inherits the node instance role can reach the EC2 IMDS and steal node-level AWS
permissions, escalating far beyond what the pod needs. A public API server with weak RBAC, or a
container escape, lets an attacker move laterally across the cluster and into the AWS account.

## Prevention
- Use IRSA / Pod Identity; block pod access to IMDS (hop limit 1, or a network policy).
- Restrict the API server endpoint (private or CIDR-limited) and enable control-plane logs.
- Enforce least-privilege RBAC; avoid cluster-admin bindings for workloads.
- Scan images, use non-root containers, and apply Pod Security Standards.
- Keep the cluster and node AMIs patched.

## Verification
Confirm IRSA is used (no broad node role), IMDS is blocked from pods, and the API endpoint is
not open to 0.0.0.0/0.
