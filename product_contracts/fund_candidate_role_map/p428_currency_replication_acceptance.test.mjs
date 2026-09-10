import test from 'node:test'
import assert from 'node:assert/strict'

const MM_PRODUCT_HEAD = '56e62824469cf96635bdc1ae3f9db0462960e052'
const mechanism = Object.freeze({ state:'INDEPENDENT_IMPLEMENTATION_REPLICATION_SUPPORTED__MECHANISM_STRENGTHENED', p426:{matched:[2.456,3.207,4.314],chronology:[-0.113,0.486,7.298,2.077],breadth:[3,4],run:34520090360,job:103015151296,artifact:10169274781}, p428:{matched:[3.285,3.079,3.670],chronology:[6.733,1.367,4.115,1.694],breadth:[4,4],run:34520380106,job:103016113294,artifact:10169383280}, protected:{ranking:false,allocation:false,sizing:false,promotion:false,strategySpec:false,runtime:false,data:false,broker:false,live:false} })

test('bind exact replicated currency-hedge MM head',()=>assert.equal(MM_PRODUCT_HEAD,'56e62824469cf96635bdc1ae3f9db0462960e052'))
test('preserve P426 scoped survivor and early weakness',()=>{assert.deepEqual(mechanism.p426.matched,[2.456,3.207,4.314]);assert.equal(mechanism.p426.chronology[0],-0.113);assert.deepEqual(mechanism.p426.breadth,[3,4])})
test('admit P428 independent implementation replication',()=>{assert.equal(mechanism.state,'INDEPENDENT_IMPLEMENTATION_REPLICATION_SUPPORTED__MECHANISM_STRENGTHENED');assert.ok(mechanism.p428.matched.every((x)=>x>0));assert.ok(mechanism.p428.chronology.every((x)=>x>0));assert.deepEqual(mechanism.p428.breadth,[4,4])})
test('retain exact research execution identities',()=>{assert.deepEqual([mechanism.p426.run,mechanism.p426.job,mechanism.p426.artifact],[34520090360,103015151296,10169274781]);assert.deepEqual([mechanism.p428.run,mechanism.p428.job,mechanism.p428.artifact],[34520380106,103016113294,10169383280])})
test('mechanism review grants no portfolio or trading authority',()=>assert.deepEqual(Object.values(mechanism.protected),Array(9).fill(false)))
