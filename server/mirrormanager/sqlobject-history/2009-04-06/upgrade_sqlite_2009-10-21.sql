ALTER TABLE host ADD COLUMN asn INT DEFAULT NULL;
ALTER TABLE host ADD COLUMN asn_clients BOOL DEFAULT TRUE;
UPDATE host SET asn=NULL, asn_clients=1;
