"""Real multipart/CLI/collect test against an isolated local HTTP service."""
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

CLI=Path(__file__).resolve().parents[1]/'scripts/paperflow.py'

class UploadHttpTests(unittest.TestCase):
    def test_upload_class_scope_and_resume_use_apis_without_reuploading(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as task_dir:
            out=Path(task_dir);pdf=out/'marked.pdf'
            with pymupdf.open() as doc:
                for _ in range(2):doc.new_page()
                doc.save(pdf)
            original=pdf.read_bytes();seen=[];errors=[];uploaded=False
            batch={'id':'newbatch','workflow_mode':'scan','grading_engine':'llm','total_pages':2,'pages_per_paper':1,'students':[{'id':'p1','index':1,'start':0},{'id':'p2','index':2,'start':1}]}
            roster={'revision':0,'semester_id':None,'classes':[]}
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def answer(self,value,status=200):
                    data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                def handle_request(self):
                    nonlocal uploaded,roster
                    method=self.command;path=urlsplit(self.path).path;seen.append((method,path))
                    raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
                    if path=='/api/uploads/upload-http-1':return self.answer({'status':'completed','batch_id':'newbatch'} if uploaded else {'status':'not_found'})
                    if path=='/api/batches' and method=='POST':
                        if uploaded:errors.append('uploaded twice')
                        if self.headers.get('Idempotency-Key')!='upload-http-1':errors.append('missing stable key')
                        msg=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                        fields={part.get_param('name',header='content-disposition'):part.get_payload(decode=True) for part in msg.iter_parts()}
                        if fields.pop('file')!=original:errors.append('file bytes changed')
                        if fields.get('has_answer_paper')!=b'false' or fields.get('workflow_mode')!=b'scan':errors.append('wrong mode')
                        uploaded=True;return self.answer(batch)
                    if path=='/api/batches/newbatch':return self.answer(batch)
                    if path=='/api/batches/newbatch/roster':
                        if method=='PUT':
                            data=json.loads(raw)
                            if data['revision']!=roster['revision']:errors.append('stale revision')
                            roster={**data,'revision':roster['revision']+1,'classes':[{'id':i} for i in data['class_ids']]}
                        return self.answer(roster)
                    errors.append('unexpected '+method+' '+path);self.answer({'detail':'unexpected'},404)
                do_GET=handle_request;do_POST=handle_request;do_PUT=handle_request
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin=f'http://127.0.0.1:{server.server_address[1]}'
            cp=out/'checkpoint.json';script=out/'request.js';result=out/'result.json';scope=out/'scope.json'
            scope.write_text(json.dumps({'semester_id':'7','class_ids':['47071'],'scope':{'source':'teaching'},'evidence_confirmed':True,'evidence_note':'Synthetic teacher selected class'}))
            system=Path('/usr/bin/python3')
            cmd=[str(system) if system.is_file() else sys.executable,str(CLI),'--base-url',origin,'--checkpoint',str(cp),'--standalone-script','--emit-script',str(script),'upload','--file',str(pdf),'--pages-per-paper','1','--key','upload-http-1','--scope-plan',str(scope)]
            env={k:v for k,v in os.environ.items() if k not in ('VIRTUAL_ENV','PAPERFLOW_PYTHON','PYTHONPATH')}
            env.update(PAPERFLOW_AUTO_UPDATE='0',PYTHONDONTWRITEBYTECODE='1')
            runner="""
const fs=require('fs');global.location={origin:process.argv[2]};global.crypto=require('crypto').webcrypto;
const f=new Blob([fs.readFileSync(process.argv[3])],{type:'application/pdf'});global.document={querySelector:()=>({files:[f]})};
const native=global.fetch;global.fetch=(path,options)=>native(new URL(path,location.origin),options);
(async()=>{const result=await eval(fs.readFileSync(process.argv[4],'utf8'));fs.writeFileSync(process.argv[5],JSON.stringify(result));if(!result.ok)throw Error(JSON.stringify(result.error));})();
"""
            try:
                for _ in range(2):
                    emitted=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True);self.assertEqual(emitted.returncode,0,emitted.stdout+emitted.stderr)
                    call=subprocess.run(['node','-',origin,str(pdf),str(script),str(result)],input=runner,text=True,capture_output=True);self.assertEqual(call.returncode,0,call.stdout+call.stderr)
                    collect=subprocess.run([sys.executable,str(CLI),'--base-url',origin,'--checkpoint',str(cp),'collect','--result',str(result)],capture_output=True,text=True)
                    self.assertEqual(collect.returncode,0,collect.stdout+collect.stderr);receipt=json.loads(collect.stdout)['result']
                    self.assertEqual(receipt['batch_id'],'newbatch');self.assertEqual(receipt['page_count_source'],'server')
                    self.assertEqual(receipt['preview_papers'][0]['pages'],[origin+'/api/batches/newbatch/pages/0?original=true&student_id=p1'])
                saved=json.loads(cp.read_text());self.assertEqual(saved['batch_id'],'newbatch');self.assertEqual(saved['upload_receipt']['sha256'],hashlib.sha256(original).hexdigest())
                self.assertEqual(sum(m=='POST' and p=='/api/batches' for m,p in seen),1)
                self.assertEqual(sum(m=='PUT' for m,p in seen),1);self.assertFalse(errors,errors)
            finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
