-- 查询单词
select * from etymology where word = 'ible';

--插入专有名词
insert into etymology(word,meaning) values('paris','巴黎');

--插入词缀
insert into etymology(word,meaning,type,nonword) values('in','','affix','1');

--插入普通单词
insert into etymology(word,meaning,origin,type) values('intend','','','affix');

--插入词源
insert into etymology(word,meaning,type,nonword) values('in','','affix','1');