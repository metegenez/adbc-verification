-- MySQL init: seed data (idempotent via INSERT IGNORE)

-- 5 regions
INSERT IGNORE INTO region VALUES
(0, 'AFRICA', 'lar deposits. blithely final packages cajole.'),
(1, 'AMERICA', 'hs use ironic, even requests.'),
(2, 'ASIA', 'ges. thinly even pinto beans ca'),
(3, 'EUROPE', 'ly final courts cajole furiously final excuse'),
(4, 'MIDDLE EAST', 'uickly special accounts cajole carefully blithely close');

-- 25 nations
INSERT IGNORE INTO nation VALUES
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
(24, 'UNITED STATES', 1, 'y final packages. slow foxes cajole quickly');

-- 5 orders
INSERT IGNORE INTO orders VALUES
(1, 370, 'O', 172799.49, '1996-01-02', '5-LOW', 'Clerk#000000951', 0, 'nstructions sleep furiously'),
(2, 781, 'O', 38426.09, '1996-12-01', '1-URGENT', 'Clerk#000000880', 0, 'foxes. pending accounts at the pending'),
(3, 1234, 'F', 205654.30, '1993-10-14', '5-LOW', 'Clerk#000000955', 0, 'sly final accounts boost'),
(4, 1369, 'O', 56000.91, '1995-10-11', '5-LOW', 'Clerk#000000124', 0, 'sits. slyly regular warthogs cajole'),
(5, 445, 'F', 105367.67, '1994-07-30', '5-LOW', 'Clerk#000000925', 0, 'quickly. bold deposits sleep slyly');

-- 5 lineitems
INSERT IGNORE INTO lineitem VALUES
(1, 1552, 93, 1, 17.00, 24710.35, 0.04, 0.02, 'N', 'O', '1996-03-13', '1996-02-12', '1996-03-22', 'DELIVER IN PERSON', 'TRUCK', 'egular courts above the'),
(1, 674, 75, 2, 36.00, 56688.12, 0.09, 0.06, 'N', 'O', '1996-04-12', '1996-02-28', '1996-04-20', 'TAKE BACK RETURN', 'MAIL', 'ly final dependencies'),
(2, 1061, 62, 1, 38.00, 37402.28, 0.00, 0.05, 'N', 'O', '1997-01-28', '1997-01-14', '1997-02-02', 'TAKE BACK RETURN', 'RAIL', 'ven requests beside the slyly'),
(3, 420, 21, 1, 45.00, 54270.90, 0.06, 0.00, 'R', 'F', '1994-02-02', '1994-01-04', '1994-02-23', 'NONE', 'AIR', 'ongside of the furiously brave acco'),
(4, 880, 81, 1, 30.00, 53850.40, 0.03, 0.08, 'N', 'O', '1996-01-10', '1995-12-14', '1996-01-18', 'DELIVER IN PERSON', 'REG AIR', 'sly final accounts according to the');

-- 3 test_data rows
INSERT IGNORE INTO test_data VALUES
(1, 'alice', 10.5),
(2, 'bob', 20.3),
(3, 'charlie', 30.1);
