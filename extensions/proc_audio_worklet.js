// proc_audio_worklet.js - custom DSP processors for proc_audio
// Registered processors: seeded-noise, bandlimited-osc, granular, resonator

class SeededNoiseProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.seed = (options.processorOptions && options.processorOptions.seed) || 12345;
    this.state = this.seed;
    this.kind = (options.processorOptions && options.processorOptions.kind) || 'white';
    this.b0=this.b1=this.b2=0;
    this.last=0;
  }
  xorshift(){
    let x=this.state;
    x^=x<<13; x^=x>>17; x^=x<<5;
    this.state=x>>>0;
    return (x>>>0)/4294967296;
  }
  process(inputs, outputs){
    const out = outputs[0][0];
    if(!out) return true;
    for(let i=0;i<out.length;i++){
      let white = this.xorshift()*2-1;
      if(this.kind==='white'){ out[i]=white; }
      else if(this.kind==='pink'){
        this.b0=0.99886*this.b0 + white*0.0555179;
        this.b1=0.99332*this.b1 + white*0.0750759;
        this.b2=0.96900*this.b2 + white*0.1538520;
        out[i]=(this.b0+this.b1+this.b2+white*0.5362)*0.11;
      } else {
        this.last = this.last + white*0.02;
        this.last = Math.max(-1,Math.min(1,this.last));
        out[i]=this.last*3.5;
      }
    }
    return true;
  }
}
registerProcessor('seeded-noise', SeededNoiseProcessor);

class BandlimitedOscProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.freq = (options.processorOptions && options.processorOptions.frequency) || 440;
    this.type = (options.processorOptions && options.processorOptions.wave) || 'sine';
    this.phase=0;
  }
  process(inputs, outputs){
    const out=outputs[0][0];
    if(!out) return true;
    const inc = this.freq/sampleRate;
    for(let i=0;i<out.length;i++){
      let v=0;
      if(this.type==='sine') v=Math.sin(this.phase*2*Math.PI);
      else if(this.type==='square') v=this.phase<0.5?1:-1;
      else if(this.type==='sawtooth') v=2*(this.phase-0.5);
      else if(this.type==='triangle') v=2*Math.abs(2*(this.phase-0.5))-1;
      out[i]=v;
      this.phase+=inc; if(this.phase>=1) this.phase-=1;
    }
    return true;
  }
}
registerProcessor('bandlimited-osc', BandlimitedOscProcessor);

class GranularProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.grainSize = (options.processorOptions && options.processorOptions.grainSize) || 0.1;
    this.pos=0;
  }
  process(inputs, outputs){
    const inp = inputs[0][0];
    const out = outputs[0][0];
    if(!inp || !out) return true;
    for(let i=0;i<out.length;i++){
      let idx = Math.floor(this.pos) % inp.length;
      let win = 0.5 - 0.5*Math.cos(2*Math.PI* (this.pos % (this.grainSize*sampleRate))/(this.grainSize*sampleRate));
      out[i]=inp[idx]*win;
      this.pos+=1;
      if(this.pos>=inp.length) this.pos=0;
    }
    return true;
  }
}
registerProcessor('granular', GranularProcessor);

class ResonatorProcessor extends AudioWorkletProcessor {
  constructor(options){
    super();
    this.freq = (options.processorOptions && options.processorOptions.frequency) || 200;
    this.decay = (options.processorOptions && options.processorOptions.decay) || 0.9;
    this.buf = new Float32Array(1024).fill(0);
    this.idx=0;
  }
  process(inputs, outputs, params){
    const inp = inputs[0][0];
    const out = outputs[0][0];
    if(!out) return true;
    for(let i=0;i<out.length;i++){
      let inputSample = inp ? inp[i] : 0;
      // simple comb resonator
      let delayed = this.buf[this.idx] || 0;
      let outSample = inputSample + delayed * this.decay;
      this.buf[this.idx]=outSample;
      this.idx=(this.idx+1)%this.buf.length;
      out[i]=outSample*0.3;
    }
    return true;
  }
}
registerProcessor('resonator', ResonatorProcessor);
