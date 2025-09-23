import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';
import sampleManholes from '@/data/sample-manholes.json';

export async function POST(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Get the body to check if we're inserting all or just one
    const body = await request.json().catch(() => ({}));
    const { index } = body;

    let dataToInsert;

    if (typeof index === 'number' && index >= 0 && index < sampleManholes.length) {
      // Insert specific manhole by index
      const sample = sampleManholes[index];
      dataToInsert = [{
        id: parseInt(sample.id.replace('sample-', '')),
        title: sample.name,
        prefecture: sample.prefecture,
        municipality: sample.city,
        location: `POINT(${sample.longitude} ${sample.latitude})`,
        pokemons: [sample.name.replace('マンホール', '')]
      }];
    } else {
      // Insert all manholes
      dataToInsert = sampleManholes.map((sample, idx) => ({
        id: idx + 1, // Use sequential IDs
        title: sample.name,
        prefecture: sample.prefecture,
        municipality: sample.city,
        location: `POINT(${sample.longitude} ${sample.latitude})`,
        pokemons: [sample.name.replace('マンホール', '')]
      }));
    }

    console.log('Attempting to insert:', dataToInsert);

    // Try to insert data
    const { data, error } = await supabase
      .from('manhole')
      .insert(dataToInsert)
      .select();

    if (error) {
      console.error('Insert error:', error);

      if (error.message.includes('row-level security')) {
        return NextResponse.json({
          success: false,
          error: 'Database access restricted by Row Level Security',
          suggestion: 'You may need to configure RLS policies or use service role key',
          rls_info: 'Check Supabase dashboard for RLS settings on manhole table'
        }, { status: 403 });
      }

      return NextResponse.json({
        success: false,
        error: error.message,
        code: error.code,
        details: error.details
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      message: `Successfully inserted ${data.length} manhole(s)`,
      data
    });

  } catch (error) {
    console.error('Request error:', error);
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    const { data, error } = await supabase
      .from('manhole')
      .select('*')
      .order('id');

    if (error) {
      return NextResponse.json({
        success: false,
        error: error.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      count: data?.length || 0,
      data,
      sample_count: sampleManholes.length
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}