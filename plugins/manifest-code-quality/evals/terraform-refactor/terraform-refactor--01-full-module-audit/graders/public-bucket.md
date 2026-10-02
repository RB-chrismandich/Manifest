---
type: llm
weight: 1
---
Score 1 only if the answer flags `aws_s3_bucket_acl.data_acl` setting `acl = "public-read"` as making the bucket's objects publicly readable — a critical data-exposure risk — AND recommends setting the ACL to `private` and/or adding an `aws_s3_bucket_public_access_block` resource with the block-public flags enabled. Score 0 otherwise.
