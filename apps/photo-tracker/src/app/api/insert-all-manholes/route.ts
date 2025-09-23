import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';
import comprehensiveManholes from '@/data/comprehensive-manholes.json';

export async function POST(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Transform comprehensive data to database format
    const transformedData = comprehensiveManholes.map((sample, idx) => ({
      id: idx + 6, // Start from 6 since we already have 1-5
      title: sample.name,
      prefecture: sample.prefecture,
      municipality: sample.city,
      location: `POINT(${sample.longitude} ${sample.latitude})`,
      pokemons: [sample.name.replace('マンホール', '')]
    }));

    console.log(`Attempting to insert ${transformedData.length} additional manholes...`);

    // Insert data
    const { data, error } = await supabase
      .from('manhole')
      .insert(transformedData)
      .select();

    if (error) {
      console.error('Insert error:', error);

      if (error.message.includes('duplicate key') || error.code === '23505') {
        return NextResponse.json({
          success: false,
          error: 'Some manholes already exist',
          suggestion: 'Try clearing the table first or use different IDs',
          error_code: error.code
        }, { status: 409 });
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
      message: `Successfully inserted ${data.length} additional manholes`,
      inserted_count: data.length,
      total_new_manholes: transformedData.length,
      data: data.slice(0, 3) // Show first 3 for verification
    });

  } catch (error) {
    console.error('Request error:', error);
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Delete all manholes
    const { error } = await supabase
      .from('manhole')
      .delete()
      .neq('id', 0); // Delete all rows

    if (error) {
      return NextResponse.json({
        success: false,
        error: error.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      message: 'All manholes deleted successfully'
    });

  } catch (error) {
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
      current_count: data?.length || 0,
      comprehensive_data_count: comprehensiveManholes.length,
      existing_data: data?.slice(0, 5), // Show first 5
      ready_to_insert: comprehensiveManholes.length
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}