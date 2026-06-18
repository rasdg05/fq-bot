import React from 'react';
import {COLORS} from '../brand/tokens';

/** Marco de telefono sobrio para envolver el showcase del bot. */
export const PhoneFrame: React.FC<{children: React.ReactNode}> = ({children}) => (
  <div
    style={{
      width: 660,
      height: 1340,
      borderRadius: 64,
      background: '#000',
      padding: 16,
      boxShadow: '0 40px 120px rgba(0,0,0,0.6)',
      border: `1px solid ${COLORS.hairline}`,
    }}
  >
    <div
      style={{
        width: '100%',
        height: '100%',
        borderRadius: 50,
        overflow: 'hidden',
        background: COLORS.bg,
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 18,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 150,
          height: 30,
          borderRadius: 18,
          background: '#000',
          zIndex: 5,
        }}
      />
      {children}
    </div>
  </div>
);
