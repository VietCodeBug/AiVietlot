import { expect,it } from 'vitest'
import { authErrorMessage,normalizeAuthEmail } from './auth-errors'
it('rejects incomplete email domains before calling password login',()=>{
 expect(()=>normalizeAuthEmail('ten@gmailcom')).toThrow('dấu chấm')
 expect(normalizeAuthEmail(' TEN@GMAIL.COM ')).toBe('ten@gmail.com')
})
it('explains invalid credentials and email confirmation separately',()=>{
 expect(authErrorMessage({code:'invalid_credentials',message:'Invalid login credentials'})).toContain('chưa tạo tài khoản')
 expect(authErrorMessage({code:'email_not_confirmed',message:'Email not confirmed'})).toContain('chưa được xác nhận')
})
