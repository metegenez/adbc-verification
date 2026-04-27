-- PostgreSQL init: seed data (idempotent via ON CONFLICT DO NOTHING)

-- 5 regions
INSERT INTO region VALUES
(0, 'AFRICA', 'lar deposits. blithely final packages cajole.'),
(1, 'AMERICA', 'hs use ironic, even requests.'),
(2, 'ASIA', 'ges. thinly even pinto beans ca'),
(3, 'EUROPE', 'ly final courts cajole furiously final excuse'),
(4, 'MIDDLE EAST', 'uickly special accounts cajole carefully blithely close')
ON CONFLICT (r_regionkey) DO NOTHING;

-- 25 nations
INSERT INTO nation VALUES
(0, 'ALGERIA', 0, 'furiously regular deposits'),
(1, 'ARGENTINA', 1, 'al foxes promise'),
(2, 'BRAZIL', 1, 'y alongside of the pending deposits'),
(3, 'CANADA', 1, 'eas hang ironic'),
(4, 'EGYPT', 4, 'y above the carefully unusual theodolites'),
(5, 'ETHIOPIA', 0, 'ven packages wake quickly'),
(6, 'FRANCE', 3, 'refully final requests'),
(7, 'GERMANY', 3, 'l platelets. regular accounts x-ray'),
(8, 'INDIA', 2, 'ss excuses cajole slyly across the packages'),
(9, 'INDONESIA', 2, 'slyly express asymptotes'),
(10, 'IRAN', 4, 'efully alongside of the slyly final dependencies'),
(11, 'IRAQ', 4, 'nic deposits boost atop the quickly final requests'),
(12, 'JAPAN', 2, 'ously. final, express gifts cajole a'),
(13, 'JORDAN', 4, 'ic deposits are blithely about the carefully regular'),
(14, 'KENYA', 0, 'pending excuses haggle furiously deposits'),
(15, 'MOROCCO', 0, 'rns. blithely bold courts among the closely regular'),
(16, 'MOZAMBIQUE', 0, 's. ironic, unusual asymptotes wake blithely r'),
(17, 'PERU', 1, 'platelets. blithely pending dependencies use fluffily'),
(18, 'CHINA', 2, 'c dependencies. furiously express notornis sleep slyly'),
(19, 'ROMANIA', 3, 'ular asymptotes are about the furious multipliers'),
(20, 'SAUDI ARABIA', 4, 'ts. silent requests haggle. closely express packages'),
(21, 'VIETNAM', 2, 'hely enticingly express accounts. even, final'),
(22, 'RUSSIA', 3, 'requests against the platelets use never according to the'),
(23, 'UNITED KINGDOM', 3, 'eans boost carefully special requests'),
(24, 'UNITED STATES', 1, 'y final packages. slow foxes cajole quickly')
ON CONFLICT (n_nationkey) DO NOTHING;

-- 5 orders
INSERT INTO orders VALUES
(1, 370, 'O', 172799.49, '1996-01-02', '5-LOW', 'Clerk#000000951', 0, 'nstructions sleep furiously'),
(2, 781, 'O', 38426.09, '1996-12-01', '1-URGENT', 'Clerk#000000880', 0, 'foxes. pending accounts at the pending'),
(3, 1234, 'F', 205654.30, '1993-10-14', '5-LOW', 'Clerk#000000955', 0, 'sly final accounts boost'),
(4, 1369, 'O', 56000.91, '1995-10-11', '5-LOW', 'Clerk#000000124', 0, 'sits. slyly regular warthogs cajole'),
(5, 445, 'F', 105367.67, '1994-07-30', '5-LOW', 'Clerk#000000925', 0, 'quickly. bold deposits sleep slyly')
ON CONFLICT (o_orderkey) DO NOTHING;

-- 5 lineitems
INSERT INTO lineitem VALUES
(1, 1552, 93, 1, 17.00, 24710.35, 0.04, 0.02, 'N', 'O', '1996-03-13', '1996-02-12', '1996-03-22', 'DELIVER IN PERSON', 'TRUCK', 'egular courts above the'),
(1, 674, 75, 2, 36.00, 56688.12, 0.09, 0.06, 'N', 'O', '1996-04-12', '1996-02-28', '1996-04-20', 'TAKE BACK RETURN', 'MAIL', 'ly final dependencies'),
(2, 1061, 62, 1, 38.00, 37402.28, 0.00, 0.05, 'N', 'O', '1997-01-28', '1997-01-14', '1997-02-02', 'TAKE BACK RETURN', 'RAIL', 'ven requests beside the slyly'),
(3, 420, 21, 1, 45.00, 54270.90, 0.06, 0.00, 'R', 'F', '1994-02-02', '1994-01-04', '1994-02-23', 'NONE', 'AIR', 'ongside of the furiously brave acco'),
(4, 880, 81, 1, 30.00, 53850.40, 0.03, 0.08, 'N', 'O', '1996-01-10', '1995-12-14', '1996-01-18', 'DELIVER IN PERSON', 'REG AIR', 'sly final accounts according to the')
ON CONFLICT (l_orderkey, l_linenumber) DO NOTHING;

-- 5 parts
INSERT INTO part VALUES
(1, 'goldenrod lace spring', 'Manufacturer#1', 'Brand#13', 'PROMO BURNISHED COPPER', 7, 'JUMBO PKG', 901.00, 'furiously reg requests'),
(2, 'blush forest saddle', 'Manufacturer#1', 'Brand#13', 'LARGE BRUSHED BRASS', 1, 'LG CASE', 902.00, 'lar accounts with the'),
(3, 'dark green antique puff', 'Manufacturer#4', 'Brand#42', 'STANDARD POLISHED BRASS', 21, 'WRAP CASE', 903.00, 'dual pinto beans'),
(4, 'hot lace khaki', 'Manufacturer#3', 'Brand#34', 'SMALL PLATED BRASS', 14, 'MED BAG', 904.00, 'the stealthy requests'),
(5, 'spring indian chiffon', 'Manufacturer#3', 'Brand#35', 'PROMO BRUSHED STEEL', 7, 'SM PKG', 905.00, 'c deposits boost slyly')
ON CONFLICT (p_partkey) DO NOTHING;

-- 5 suppliers
INSERT INTO supplier VALUES
(1, 'Supplier#000000001', 'N kD4on9OM Ipw3,gf0JBoq', 17, '27-918-335-1736', 5755.94, 'final deposits among the slyly express gifts'),
(2, 'Supplier#000000002', '89eJ5ksX3ImxJQBvxObC,', 5, '15-679-861-2259', 4032.68, 'blithely bold packages express'),
(3, 'Supplier#000000003', 'gyCsewaC4p', 1, '11-383-516-1199', 4192.40, 'carefully final packages cajole fluffily'),
(4, 'Supplier#000000004', 'kTGpJqO8HOrfbh', 14, '24-696-997-4969', 5300.37, 'slyly bold dependencies wake'),
(5, 'Supplier#000000005', 'd8eFhrA8b', 9, '19-393-671-5272', 8014.30, 'closely express theodolites across the')
ON CONFLICT (s_suppkey) DO NOTHING;

-- 5 partsupps
INSERT INTO partsupp VALUES
(1, 2, 3325, 771.64, 'furiously even instructions. furiously ironic theodolites are green,'),
(1, 3, 8076, 993.49, 'luffily according to the slyly regular packages. regular packages around the'),
(2, 3, 3956, 337.09, 'carefully pending pinto beans. quickly silent packages are among the'),
(3, 4, 4069, 905.44, 'ending packages. furiously unusual requests are fluffily'),
(4, 3, 8895, 378.49, 'cording to the final, final theodolites. blithely final packages sleep')
ON CONFLICT (ps_partkey, ps_suppkey) DO NOTHING;

-- 5 customers
INSERT INTO customer VALUES
(1, 'Customer#000000001', 'IVhzIApeRb ot,c,E', 15, '25-989-741-2988', 711.56, 'BUILDING', 'furiously even instructions above the slyly silent instructions'),
(2, 'Customer#000000002', 'XSTf4,NCwDVaWNe6tEgvw', 13, '23-768-687-3665', 121.65, 'AUTOMOBILE', 'the slyly bold accounts. quickly final instructions cajole blithely'),
(3, 'Customer#000000003', 'MG9kdTD2WBHm', 1, '11-719-748-3364', 7498.12, 'FURNITURE', 'posits sleep slyly carefully regular frets. carefully final'),
(4, 'Customer#000000004', 'XxVSyxsKBtn', 4, '14-128-190-5944', 2866.83, 'MACHINERY', 'ackages. accounts according to the furiously even deposits haggle'),
(5, 'Customer#000000005', 'KvpyuHCplrB84W', 17, '27-750-860-3807', 5864.25, 'BUILDING', 'lyly express accounts. regular ideas nag slyly')
ON CONFLICT (c_custkey) DO NOTHING;

-- 3 test_data rows
INSERT INTO test_data VALUES
(1, 'Alice', 10.5),
(2, 'Bob', 20.3),
(3, 'Charlie', 30.1)
ON CONFLICT (id) DO NOTHING;

-- 3 departments (cross-join)
INSERT INTO departments VALUES
(10, 'Engineering'),
(20, 'Marketing'),
(30, 'Sales')
ON CONFLICT (dept_id) DO NOTHING;
